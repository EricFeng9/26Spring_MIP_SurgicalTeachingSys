package com.retinal.auth;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Locale;
import java.util.Map;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

public final class AuthHttpServer {
    private final HttpServer server;
    private final AuthService authService;
    private final EvaluationService evaluationService;
    private final CaseService caseService;
    private final SubmissionService submissionService;

    public AuthHttpServer(int port, AuthService authService, DatabaseManager db) throws IOException, SQLException {
        this.server = HttpServer.create(new InetSocketAddress(port), 0);
        this.authService = authService;
        this.evaluationService = new EvaluationService();
        this.caseService = new CaseService();
        this.submissionService = new SubmissionService(db, this.evaluationService);
        registerRoutes();
    }

    public static AuthHttpServer createDefault(int port) throws SQLException, IOException {
        DatabaseManager db = DatabaseManager.fromEnv();
        db.initialize();
        return new AuthHttpServer(port, new AuthService(db), db);
    }

    public void start() {
        server.start();
        System.out.println("Auth API listening on http://localhost:" + server.getAddress().getPort());
    }

    public void stop(int delaySeconds) {
        server.stop(delaySeconds);
    }

    private void registerRoutes() {
        // 静态文件访问接口：/api/file?path=相对路径
        server.createContext("/api/file", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }
            String relPath = queryParam(exchange, "path");
            if (relPath == null || relPath.isBlank()) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("query 参数 path 不能为空。"));
                return;
            }
            // 只允许访问 data/sessions 和 data/cases 及 evaluation/test/sample_data 目录下的文件
            String safeRoot1 = "data/sessions/";
            String safeRoot2 = "data/cases/";
            String safeRoot3 = "evaluation/test/sample_data/";
            String safeRoot4 = "data/";
            String safeRoot5 = "evaluation/test/output/";
            String safeRoot6 = "evaluation/test/sample_data/Temp770298_sample/R/";
            String[] allowedRoots = {safeRoot1, safeRoot2, safeRoot3, safeRoot4, safeRoot5, safeRoot6};
            relPath = relPath.replace("\\", "/");
            boolean allowed = false;
            for (String root : allowedRoots) {
                if (relPath.startsWith(root)) {
                    allowed = true;
                    break;
                }
            }
            if (!allowed) {
                writeJson(exchange, 403, HttpJsonUtil.buildErrorJson("禁止访问该路径: " + relPath));
                return;
            }
            java.nio.file.Path filePath = java.nio.file.Paths.get(System.getProperty("user.dir")).resolve(relPath);
            if (!java.nio.file.Files.exists(filePath) || !java.nio.file.Files.isRegularFile(filePath)) {
                writeJson(exchange, 404, HttpJsonUtil.buildErrorJson("文件不存在: " + relPath));
                return;
            }
            String contentType = "application/octet-stream";
            String lower = relPath.toLowerCase(Locale.ROOT);
            if (lower.endsWith(".png")) contentType = "image/png";
            else if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) contentType = "image/jpeg";
            else if (lower.endsWith(".json")) contentType = "application/json";
            try {
                byte[] bytes = java.nio.file.Files.readAllBytes(filePath);
                writeBytes(exchange, 200, bytes, contentType);
            } catch (IOException e) {
                writeJson(exchange, 500, HttpJsonUtil.buildErrorJson("文件读取失败: " + e.getMessage()));
            }
        });
        server.createContext("/api/health", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }
            writeJson(exchange, 200, "{\"success\":true,\"message\":\"ok\"}");
        });

        server.createContext("/api/auth/register", new JsonPostHandler() {
            @Override
            protected void handleJson(HttpExchange exchange, String body) throws IOException {
                String username = HttpJsonUtil.readJsonString(body, "username");
                String password = HttpJsonUtil.readJsonString(body, "password");
                if (username == null || password == null) {
                    writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("请求体必须包含 username 和 password。"));
                    return;
                }

                AuthResult result = authService.register(username, password);
                writeJson(exchange, result.success() ? 200 : 400, HttpJsonUtil.buildAuthResultJson(result));
            }
        });

        server.createContext("/api/auth/login", new JsonPostHandler() {
            @Override
            protected void handleJson(HttpExchange exchange, String body) throws IOException {
                String username = HttpJsonUtil.readJsonString(body, "username");
                String password = HttpJsonUtil.readJsonString(body, "password");
                if (username == null || password == null) {
                    writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("请求体必须包含 username 和 password。"));
                    return;
                }

                AuthResult result = authService.login(username, password);
                writeJson(exchange, result.success() ? 200 : 401, HttpJsonUtil.buildAuthResultJson(result));
            }
        });

        server.createContext("/api/auth/logout", new JsonPostHandler() {
            @Override
            protected void handleJson(HttpExchange exchange, String body) throws IOException {
                String token = HttpJsonUtil.readJsonString(body, "token");
                if (token == null) {
                    writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("请求体必须包含 token。"));
                    return;
                }

                AuthResult result = authService.logout(token);
                writeJson(exchange, result.success() ? 200 : 400, HttpJsonUtil.buildAuthResultJson(result));
            }
        });

        server.createContext("/api/evaluation/run", new JsonPostHandler() {
            @Override
            protected void handleJson(HttpExchange exchange, String body) throws IOException {
                EvaluationService.EvaluationRequest request = EvaluationService.EvaluationRequest.fromJson(body);
                if (!request.isValid()) {
                    writeJson(exchange, 400, HttpJsonUtil.buildErrorJson(request.validationError()));
                    return;
                }

                try {
                    String reportJson = evaluationService.run(request);
                    writeJson(exchange, 200, reportJson);
                } catch (IOException | InterruptedException e) {
                    if (e instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                    writeJson(exchange, 500, HttpJsonUtil.buildErrorJson(e.getMessage()));
                }
            }
        });

        server.createContext("/api/session/submit", new JsonPostHandler() {
            @Override
            protected void handleJson(HttpExchange exchange, String body) throws IOException {
                SubmissionService.SubmitRequest request = SubmissionService.SubmitRequest.fromJson(body);
                if (!request.isValid()) {
                    writeJson(exchange, 400, HttpJsonUtil.buildErrorJson(request.validationError()));
                    return;
                }

                try {
                    String responseJson = submissionService.submit(request);
                    writeJson(exchange, 200, responseJson);
                } catch (IOException | InterruptedException | SQLException e) {
                    if (e instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                    writeJson(exchange, 500, HttpJsonUtil.buildErrorJson(e.getMessage()));
                }
            }
        });

        server.createContext("/api/session/submit-upload", exchange -> {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeJson(exchange, 204, "");
                return;
            }
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }

            String contentType = firstHeader(exchange.getRequestHeaders(), "Content-Type");
            if (contentType == null || !contentType.toLowerCase(Locale.ROOT).startsWith("multipart/form-data")) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("Content-Type 必须为 multipart/form-data。"));
                return;
            }

            byte[] raw = exchange.getRequestBody().readAllBytes();
            Map<String, MultipartFormDataParser.Part> parts;
            try {
                parts = MultipartFormDataParser.parse(raw, contentType);
            } catch (IOException e) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("multipart 解析失败: " + e.getMessage()));
                return;
            }

            String userId = readTextPart(parts, "user_id");
            String caseId = readTextPart(parts, "case_id");
            String questionJsonPath = readTextPart(parts, "question_json_path");
            String pythonExecutable = readTextPart(parts, "python_executable");
            String projectRoot = readTextPart(parts, "project_root");

            String playerJson = readTextPart(parts, "player_json");
            MultipartFormDataParser.Part playerJsonFile = parts.get("player_json_file");
            if ((playerJson == null || playerJson.isBlank()) && playerJsonFile != null && playerJsonFile.bytes().length > 0) {
                playerJson = playerJsonFile.asUtf8Text();
            }

            MultipartFormDataParser.Part postopImage = parts.get("postop_image_file");
            if (postopImage == null) {
                postopImage = parts.get("player_image_file");
            }

            byte[] imageBytes = null;
            String imageMime = readTextPart(parts, "postop_image_mime");
            if (imageMime == null || imageMime.isBlank()) {
                imageMime = readTextPart(parts, "player_image_mime");
            }
            if (postopImage != null && postopImage.bytes().length > 0) {
                imageBytes = postopImage.bytes();
                if (imageMime == null || imageMime.isBlank()) {
                    imageMime = postopImage.contentType();
                }
            }

            SubmissionService.UploadedSubmitRequest request = new SubmissionService.UploadedSubmitRequest(
                    userId,
                    caseId,
                    playerJson,
                    questionJsonPath,
                    imageBytes,
                    imageMime,
                    pythonExecutable,
                    projectRoot
            );
            if (!request.isValid()) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson(request.validationError()));
                return;
            }

            try {
                String responseJson = submissionService.submitUploaded(request);
                writeJson(exchange, 200, responseJson);
            } catch (IOException | InterruptedException | SQLException e) {
                if (e instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
                writeJson(exchange, 500, HttpJsonUtil.buildErrorJson(e.getMessage()));
            }
        });

        server.createContext("/api/cases/detail", exchange -> {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeJson(exchange, 204, "");
                return;
            }
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }

            String caseId = queryParam(exchange, "caseId");
            if (caseId == null || caseId.isBlank()) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("query 参数 caseId 不能为空。"));
                return;
            }

            String caseJson = caseService.getCaseDetailJson(caseId);
            if (caseJson == null) {
                writeJson(exchange, 404, HttpJsonUtil.buildErrorJson("未找到关卡: " + caseId));
                return;
            }
            writeJson(exchange, 200, caseJson);
        });

        server.createContext("/api/cases/preop-image", exchange -> {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeJson(exchange, 204, "");
                return;
            }
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }

            String caseId = queryParam(exchange, "caseId");
            if (caseId == null || caseId.isBlank()) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("query 参数 caseId 不能为空。"));
                return;
            }

            CaseService.ImageFile imageFile = caseService.getCaseImage(caseId, "preop");
            if (imageFile == null) {
                writeJson(exchange, 404, HttpJsonUtil.buildErrorJson("未找到关卡术前图: " + caseId));
                return;
            }
            writeBytes(exchange, 200, imageFile.bytes(), imageFile.contentType());
        });
    }

    private static void writeMethodNotAllowed(HttpExchange exchange) throws IOException {
        writeJson(exchange, 405, HttpJsonUtil.buildErrorJson("Method Not Allowed"));
    }

    private static void writeJson(HttpExchange exchange, int statusCode, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", "application/json; charset=utf-8");
        headers.set("Access-Control-Allow-Origin", "*");
        headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
        headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");

        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (var responseBody = exchange.getResponseBody()) {
            responseBody.write(bytes);
        }
    }

    private static void writeBytes(HttpExchange exchange, int statusCode, byte[] bytes, String contentType) throws IOException {
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", contentType != null ? contentType : "application/octet-stream");
        headers.set("Access-Control-Allow-Origin", "*");
        headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
        headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");

        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (var responseBody = exchange.getResponseBody()) {
            responseBody.write(bytes);
        }
    }

    private static String queryParam(HttpExchange exchange, String key) {
        String query = exchange.getRequestURI().getRawQuery();
        if (query == null || query.isBlank()) {
            return null;
        }

        String[] pairs = query.split("&");
        for (String pair : pairs) {
            String[] kv = pair.split("=", 2);
            if (kv.length != 2) {
                continue;
            }
            String k = URLDecoder.decode(kv[0], StandardCharsets.UTF_8);
            if (!key.equals(k)) {
                continue;
            }
            return URLDecoder.decode(kv[1], StandardCharsets.UTF_8);
        }
        return null;
    }

    private static String firstHeader(Headers headers, String key) {
        if (headers == null || key == null) {
            return null;
        }
        return headers.getFirst(key);
    }

    private static String readTextPart(Map<String, MultipartFormDataParser.Part> parts, String key) {
        MultipartFormDataParser.Part part = parts.get(key);
        if (part == null || part.bytes().length == 0) {
            return null;
        }
        String text = part.asUtf8Text();
        return text != null ? text.trim() : null;
    }

    private abstract static class JsonPostHandler implements HttpHandler {
        @Override
        public final void handle(HttpExchange exchange) throws IOException {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeJson(exchange, 204, "");
                return;
            }

            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }

            String body = readBody(exchange.getRequestBody());
            handleJson(exchange, body);
        }

        protected abstract void handleJson(HttpExchange exchange, String body) throws IOException;

        private static String readBody(InputStream bodyStream) throws IOException {
            byte[] raw = bodyStream.readAllBytes();
            return new String(raw, StandardCharsets.UTF_8);
        }
    }
}
