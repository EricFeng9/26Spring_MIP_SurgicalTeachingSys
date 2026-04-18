package com.retinal.auth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class EvaluationService {
    private static final long DEFAULT_TIMEOUT_SECONDS = 600L;

    public String run(EvaluationRequest request) throws IOException, InterruptedException {
        Path projectRoot = request.projectRoot() != null
                ? Paths.get(request.projectRoot()).toAbsolutePath().normalize()
                : findProjectRoot();

        Path evaluatorScript = request.evaluatorScriptPath() != null
                ? Paths.get(request.evaluatorScriptPath()).toAbsolutePath().normalize()
                : projectRoot.resolve("evaluation/main/src/evaluator.py");

        Path configPath = request.configJsonPath() != null
                ? Paths.get(request.configJsonPath()).toAbsolutePath().normalize()
                : projectRoot.resolve("evaluation/docs/config.json");

        Path questionPath = request.questionJsonPath() != null
                ? Paths.get(request.questionJsonPath()).toAbsolutePath().normalize()
                : null;
        Path playerPath = request.playerJsonPath() != null
                ? Paths.get(request.playerJsonPath()).toAbsolutePath().normalize()
                : null;

        if ((questionPath == null || playerPath == null) && request.sampleRoot() != null) {
            SamplePair pair = findSamplePair(Paths.get(request.sampleRoot()).toAbsolutePath().normalize());
            questionPath = pair.questionPath();
            playerPath = pair.playerPath();
        }

        if (questionPath == null || playerPath == null) {
            throw new IllegalArgumentException("请求必须提供 sample_root，或同时提供 question_json_path 与 player_json_path。");
        }

        Path outputPath = request.scoringOutputJsonPath() != null
                ? Paths.get(request.scoringOutputJsonPath()).toAbsolutePath().normalize()
                : defaultOutputPath(projectRoot, request.sampleRoot(), playerPath);

        Files.createDirectories(outputPath.getParent());

        List<String> command = new ArrayList<>();
        command.add(request.pythonExecutable() != null ? request.pythonExecutable() : "python");
        command.add("-c");
        command.add(buildRunnerScript());
        command.add(questionPath.toString());
        command.add(playerPath.toString());
        command.add(outputPath.toString());
        command.add(configPath.toString());
        command.add(evaluatorScript.toString());

        ProcessBuilder processBuilder = new ProcessBuilder(command);
        processBuilder.directory(projectRoot.toFile());
        processBuilder.redirectErrorStream(false);

        Process process = processBuilder.start();
        Long timeoutValue = request.timeoutSeconds();
        long timeoutSeconds = DEFAULT_TIMEOUT_SECONDS;
        if (timeoutValue != null) {
            timeoutSeconds = timeoutValue;
        }
        boolean finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new IOException("Python 评估进程超时。");
        }

        String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        int exitCode = process.exitValue();
        if (exitCode != 0) {
            StringBuilder message = new StringBuilder();
            message.append("Python 评估失败，exitCode=").append(exitCode);
            if (!stderr.isEmpty()) {
                message.append("; stderr=").append(stderr);
            }
            if (!stdout.isEmpty()) {
                message.append("; stdout=").append(stdout);
            }
            throw new IOException(message.toString());
        }

        if (!Files.exists(outputPath)) {
            throw new IOException("Python 已完成但未生成报告文件: " + outputPath);
        }

        return Files.readString(outputPath, StandardCharsets.UTF_8);
    }

    private static String buildRunnerScript() {
        return String.join("\n",
                "import importlib.util",
                "import pathlib",
                "import sys",
                "question_path = sys.argv[1]",
                "player_path = sys.argv[2]",
                "output_path = sys.argv[3]",
                "config_path = sys.argv[4]",
                "evaluator_path = sys.argv[5]",
                "evaluator_file = pathlib.Path(evaluator_path)",
                "sys.path.insert(0, str(evaluator_file.parent))",
                "spec = importlib.util.spec_from_file_location('evaluator', evaluator_path)",
                "module = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(module)",
                "status, msg = module.evaluate(question_path, player_path, output_path, config_path)",
                "print(f'status={status}')",
                "print(f'message={msg}')",
                "sys.exit(0 if status == 1 else 1)");
    }

    private static Path findProjectRoot() throws IOException {
        Path current = Paths.get("").toAbsolutePath().normalize();
        while (current != null) {
            if (Files.exists(current.resolve("evaluation/main/src/evaluator.py"))) {
                return current;
            }
            current = current.getParent();
        }
        throw new IOException("无法定位项目根目录，请通过 project_root 明确指定。");
    }

    private static Path defaultOutputPath(Path projectRoot, String sampleRoot, Path playerPath) {
        if (sampleRoot != null && !sampleRoot.isBlank()) {
            Path sampleRootPath = Paths.get(sampleRoot).toAbsolutePath().normalize();
            String sampleName = sampleRootPath.getFileName() != null ? sampleRootPath.getFileName().toString() : "evaluation";
            return projectRoot.resolve("evaluation/test/output").resolve(sampleName + "_output.json");
        }

        String fileName = playerPath.getFileName().toString();
        if (fileName.endsWith("_simplayer.json")) {
            return playerPath.resolveSibling(fileName.replace("_simplayer.json", "_output.json"));
        }
        return playerPath.resolveSibling(fileName + ".output.json");
    }

    private static SamplePair findSamplePair(Path sampleRoot) throws IOException {
        if (!Files.isDirectory(sampleRoot)) {
            throw new IOException("sample_root 不存在或不是目录: " + sampleRoot);
        }

        List<Path> candidates = new ArrayList<>();
        try (var stream = Files.walk(sampleRoot)) {
            stream.filter(path -> Files.isRegularFile(path) && path.getFileName().toString().endsWith("_simgt.json"))
                    .forEach(gtPath -> {
                        Path playerPath = Paths.get(gtPath.toString().replace("_simgt.json", "_simplayer.json"));
                        if (Files.exists(playerPath)) {
                            candidates.add(gtPath);
                        }
                    });
        }

        if (candidates.isEmpty()) {
            throw new IOException("在 sample_root 中未找到可用的 _simgt.json / _simplayer.json 配对: " + sampleRoot);
        }

        candidates.sort(Comparator.comparing(Path::toString));
        Path questionPath = candidates.get(0);
        Path playerPath = Paths.get(questionPath.toString().replace("_simgt.json", "_simplayer.json"));
        return new SamplePair(questionPath, playerPath);
    }

    public record EvaluationRequest(
            String sampleRoot,
            String questionJsonPath,
            String playerJsonPath,
            String configJsonPath,
            String scoringOutputJsonPath,
            String pythonExecutable,
            String evaluatorScriptPath,
            String projectRoot,
            Long timeoutSeconds
    ) {
        public static EvaluationRequest fromJson(String json) {
            return new EvaluationRequest(
                    HttpJsonUtil.readJsonString(json, "sample_root"),
                    HttpJsonUtil.readJsonString(json, "question_json_path"),
                    HttpJsonUtil.readJsonString(json, "player_json_path"),
                    HttpJsonUtil.readJsonString(json, "config_json_path"),
                    HttpJsonUtil.readJsonString(json, "scoring_output_json_path"),
                    HttpJsonUtil.readJsonString(json, "python_executable"),
                    HttpJsonUtil.readJsonString(json, "evaluator_script_path"),
                    HttpJsonUtil.readJsonString(json, "project_root"),
                    parseLong(HttpJsonUtil.readJsonString(json, "timeout_seconds"))
            );
        }

        public boolean isValid() {
            return (sampleRoot != null && !sampleRoot.isBlank()) ||
                    (questionJsonPath != null && !questionJsonPath.isBlank() && playerJsonPath != null && !playerJsonPath.isBlank());
        }

        public String validationError() {
            return "请求必须包含 sample_root，或者同时包含 question_json_path 与 player_json_path。";
        }

        private static Long parseLong(String value) {
            if (value == null || value.isBlank()) {
                return null;
            }
            try {
                return Long.valueOf(value.trim());
            } catch (NumberFormatException e) {
                return null;
            }
        }
    }

    private record SamplePair(Path questionPath, Path playerPath) {
    }
}