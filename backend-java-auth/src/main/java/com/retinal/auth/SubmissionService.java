package com.retinal.auth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Instant;
import java.util.Base64;
import java.util.UUID;

public final class SubmissionService {
    private final DatabaseManager db;
    private final EvaluationService evaluationService;
    private final Path sessionsRoot;

    public SubmissionService(DatabaseManager db, EvaluationService evaluationService) throws SQLException {
        this.db = db;
        this.evaluationService = evaluationService;
        this.sessionsRoot = Paths.get("data", "sessions").toAbsolutePath().normalize();
        ensureSessionTable();
    }

    public String submit(SubmitRequest request) throws IOException, InterruptedException, SQLException {
        String sessionId = "SESS_" + Instant.now().toEpochMilli() + "_" + UUID.randomUUID().toString().substring(0, 8);
        Path sessionDir = sessionsRoot.resolve(sessionId).normalize();
        Files.createDirectories(sessionDir);

        Path playerJsonPath = sessionDir.resolve("player_input.json");
        Files.writeString(playerJsonPath, request.playerJson(), StandardCharsets.UTF_8);

        String playerImagePathValue = null;
        if (request.playerImageBase64() != null && !request.playerImageBase64().isBlank()) {
            byte[] imageBytes = decodeBase64Image(request.playerImageBase64());
            String imageExt = request.playerImageMime() != null && request.playerImageMime().toLowerCase().contains("jpeg")
                    ? "jpg"
                    : "png";
            Path playerImagePath = sessionDir.resolve("player_operation." + imageExt);
            Files.write(playerImagePath, imageBytes);
            playerImagePathValue = playerImagePath.toString();
        }

        Path questionJsonPath = request.questionJsonPath() != null && !request.questionJsonPath().isBlank()
            ? Paths.get(request.questionJsonPath()).toAbsolutePath().normalize()
            : resolveQuestionPath(request.caseId());
        if (questionJsonPath == null) {
            throw new IOException("未找到关卡 JSON: " + request.caseId());
        }

        String evalProjectRoot = request.projectRoot();
        if (evalProjectRoot == null || evalProjectRoot.isBlank()) {
            evalProjectRoot = detectProjectRootFromQuestionPath(questionJsonPath);
        }

        Path reportPath = sessionDir.resolve("report.json");
        EvaluationService.EvaluationRequest evalRequest = new EvaluationService.EvaluationRequest(
                null,
                questionJsonPath.toString(),
                playerJsonPath.toString(),
                null,
                reportPath.toString(),
                request.pythonExecutable() != null ? request.pythonExecutable() : "python",
                null,
                evalProjectRoot,
                null
        );

        String reportJson = evaluationService.run(evalRequest);

        String combinedPath = reportPath.toString().replace(".json", "_combined_overlay.png");
        String playerOverlayPath = reportPath.toString().replace(".json", "_player_overlay.png");
        String gtOverlayPath = reportPath.toString().replace(".json", "_gt_overlay.png");

        // 统一返回相对 user.dir 的路径
        String userDir = System.getProperty("user.dir").replace("\\", "/");
        String relPlayerOverlayPath = relativizeToUserDir(playerOverlayPath, userDir);
        String relGtOverlayPath = relativizeToUserDir(gtOverlayPath, userDir);
        String relCombinedPath = relativizeToUserDir(combinedPath, userDir);
        String relPlayerJsonPath = relativizeToUserDir(playerJsonPath.toString(), userDir);
        String relPlayerImagePath = playerImagePathValue != null ? relativizeToUserDir(playerImagePathValue, userDir) : null;
        String relReportPath = relativizeToUserDir(reportPath.toString(), userDir);

        saveMetadata(
                sessionId,
                request.userId(),
                request.caseId(),
                relPlayerJsonPath,
                relPlayerImagePath,
                relReportPath,
                relPlayerOverlayPath,
                relGtOverlayPath,
                relCombinedPath
        );

        return buildSubmitResponseJson(
                sessionId,
                reportJson,
                relPlayerJsonPath,
                relPlayerImagePath,
                relReportPath,
                relPlayerOverlayPath,
                relGtOverlayPath,
                relCombinedPath
        );
    }

    // 将绝对路径转为 user.dir 下的相对路径，保证前端 URL 可用
    private static String relativizeToUserDir(String absPath, String userDir) {
        String normAbs = absPath.replace("\\", "/");
        if (normAbs.startsWith(userDir + "/")) {
            return normAbs.substring(userDir.length() + 1);
        }
        return normAbs;
    }

    public String submitUploaded(UploadedSubmitRequest request) throws IOException, InterruptedException, SQLException {
        String imageBase64 = null;
        if (request.playerImageBytes() != null && request.playerImageBytes().length > 0) {
            imageBase64 = Base64.getEncoder().encodeToString(request.playerImageBytes());
        }

        SubmitRequest normalized = new SubmitRequest(
                request.userId(),
                request.caseId(),
                request.playerJson(),
                request.questionJsonPath(),
                imageBase64,
                request.playerImageMime(),
                request.pythonExecutable(),
                request.projectRoot()
        );
        return submit(normalized);
    }

    private void ensureSessionTable() throws SQLException {
        String sql = "CREATE TABLE IF NOT EXISTS " + DatabaseManager.SCHEMA_NAME + ".session_submissions ("
                + "id BIGSERIAL PRIMARY KEY,"
                + "session_id VARCHAR(96) NOT NULL UNIQUE,"
                + "user_id VARCHAR(96) NOT NULL,"
                + "case_id VARCHAR(96) NOT NULL,"
                + "player_json_path TEXT NOT NULL,"
                + "player_image_path TEXT NULL,"
                + "report_json_path TEXT NOT NULL,"
                + "overlay_player_path TEXT NULL,"
                + "overlay_gt_path TEXT NULL,"
                + "overlay_combined_path TEXT NULL,"
                + "created_at VARCHAR(64) NOT NULL"
                + ");";

        try (Connection conn = db.getConnection(); Statement stmt = conn.createStatement()) {
            stmt.executeUpdate(sql);
        }
    }

    private void saveMetadata(
            String sessionId,
            String userId,
            String caseId,
            String playerJsonPath,
            String playerImagePath,
            String reportJsonPath,
            String overlayPlayerPath,
            String overlayGtPath,
            String overlayCombinedPath
    ) throws SQLException {
        String insertSql = "INSERT INTO " + DatabaseManager.SCHEMA_NAME
                + ".session_submissions(session_id, user_id, case_id, player_json_path, player_image_path, report_json_path, overlay_player_path, overlay_gt_path, overlay_combined_path, created_at) "
                + "VALUES(?,?,?,?,?,?,?,?,?,?)";

        try (Connection conn = db.getConnection(); PreparedStatement stmt = conn.prepareStatement(insertSql)) {
            stmt.setString(1, sessionId);
            stmt.setString(2, userId);
            stmt.setString(3, caseId);
            stmt.setString(4, playerJsonPath);
            stmt.setString(5, playerImagePath);
            stmt.setString(6, reportJsonPath);
            stmt.setString(7, overlayPlayerPath);
            stmt.setString(8, overlayGtPath);
            stmt.setString(9, overlayCombinedPath);
            stmt.setString(10, Instant.now().toString());
            stmt.executeUpdate();
        }
    }

    private Path resolveQuestionPath(String caseId) {
        String safeCaseId = sanitize(caseId);
        if (safeCaseId.isBlank()) {
            return null;
        }

        Path nested = Paths.get("data", "cases", safeCaseId, safeCaseId + ".json").toAbsolutePath().normalize();
        if (Files.isRegularFile(nested)) {
            return nested;
        }

        Path flat = Paths.get("data", "cases", safeCaseId + ".json").toAbsolutePath().normalize();
        if (Files.isRegularFile(flat)) {
            return flat;
        }

        return null;
    }

    private static String detectProjectRootFromQuestionPath(Path questionJsonPath) {
        if (questionJsonPath == null) {
            return null;
        }

        Path current = questionJsonPath.toAbsolutePath().normalize();
        if (Files.isRegularFile(current)) {
            current = current.getParent();
        }

        while (current != null) {
            Path evaluator = current.resolve("evaluation/main/src/evaluator.py");
            if (Files.isRegularFile(evaluator)) {
                return current.toString();
            }
            current = current.getParent();
        }

        return null;
    }

    private static String sanitize(String value) {
        if (value == null) {
            return "";
        }
        return value.trim().replaceAll("[^a-zA-Z0-9_\\-]", "");
    }

    private static byte[] decodeBase64Image(String raw) {
        String value = raw.trim();
        int commaIdx = value.indexOf(',');
        if (value.startsWith("data:") && commaIdx > 0) {
            value = value.substring(commaIdx + 1);
        }
        return Base64.getDecoder().decode(value);
    }

    private static String buildSubmitResponseJson(
            String sessionId,
            String reportJson,
            String playerJsonPath,
            String playerImagePath,
            String reportJsonPath,
            String overlayPlayerPath,
            String overlayGtPath,
            String overlayCombinedPath
    ) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"success\":true,");
        sb.append("\"session_id\":\"").append(escapeJson(sessionId)).append("\",");
        sb.append("\"report\":").append(reportJson).append(",");
        sb.append("\"paths\":{");
        sb.append("\"player_json_path\":\"").append(escapeJson(playerJsonPath)).append("\",");
        if (playerImagePath != null) {
            sb.append("\"player_image_path\":\"").append(escapeJson(playerImagePath)).append("\",");
        } else {
            sb.append("\"player_image_path\":null,");
        }
        sb.append("\"report_json_path\":\"").append(escapeJson(reportJsonPath)).append("\",");
        sb.append("\"overlay_player_path\":\"").append(escapeJson(overlayPlayerPath)).append("\",");
        sb.append("\"overlay_gt_path\":\"").append(escapeJson(overlayGtPath)).append("\",");
        sb.append("\"overlay_combined_path\":\"").append(escapeJson(overlayCombinedPath)).append("\",");

        // 新增：拼接图片 URL 字段，供前端直接访问
        if (overlayGtPath != null && !overlayGtPath.isEmpty()) {
            sb.append("\"overlay_gt_url\":\"/api/file?path=").append(escapeJson(overlayGtPath)).append("\",");
        } else {
            sb.append("\"overlay_gt_url\":null,");
        }
        if (overlayCombinedPath != null && !overlayCombinedPath.isEmpty()) {
            sb.append("\"overlay_combined_url\":\"/api/file?path=").append(escapeJson(overlayCombinedPath)).append("\"");
        } else {
            sb.append("\"overlay_combined_url\":null");
        }
        sb.append("}");
        sb.append("}");
        return sb.toString();
    }

    private static String escapeJson(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder out = new StringBuilder(value.length() + 16);
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '\\':
                    out.append("\\\\");
                    break;
                case '"':
                    out.append("\\\"");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    out.append(ch);
                    break;
            }
        }
        return out.toString();
    }

    public record SubmitRequest(
            String userId,
            String caseId,
            String playerJson,
            String questionJsonPath,
            String playerImageBase64,
            String playerImageMime,
            String pythonExecutable,
            String projectRoot
    ) {
        public static SubmitRequest fromJson(String json) {
            String imageBase64 = HttpJsonUtil.readJsonString(json, "player_image_base64");
            if (imageBase64 == null || imageBase64.isBlank()) {
                imageBase64 = HttpJsonUtil.readJsonString(json, "postop_image_base64");
            }
            if (imageBase64 == null || imageBase64.isBlank()) {
                imageBase64 = HttpJsonUtil.readJsonString(json, "postop_image");
            }

            String imageMime = HttpJsonUtil.readJsonString(json, "player_image_mime");
            if (imageMime == null || imageMime.isBlank()) {
                imageMime = HttpJsonUtil.readJsonString(json, "postop_image_mime");
            }

            return new SubmitRequest(
                    HttpJsonUtil.readJsonValueAsString(json, "user_id"),
                    HttpJsonUtil.readJsonString(json, "case_id"),
                    HttpJsonUtil.readJsonString(json, "player_json"),
                    HttpJsonUtil.readJsonString(json, "question_json_path"),
                    imageBase64,
                    imageMime,
                    HttpJsonUtil.readJsonString(json, "python_executable"),
                    HttpJsonUtil.readJsonString(json, "project_root")
            );
        }

        public boolean isValid() {
            return userId != null && !userId.isBlank()
                    && caseId != null && !caseId.isBlank()
                    && playerJson != null && !playerJson.isBlank();
        }

        public String validationError() {
            return "请求必须包含 user_id、case_id、player_json；player_image_base64 可选。";
        }
    }

    public record UploadedSubmitRequest(
            String userId,
            String caseId,
            String playerJson,
            String questionJsonPath,
            byte[] playerImageBytes,
            String playerImageMime,
            String pythonExecutable,
            String projectRoot
    ) {
        public boolean isValid() {
            return userId != null && !userId.isBlank()
                    && caseId != null && !caseId.isBlank()
                    && playerJson != null && !playerJson.isBlank();
        }

        public String validationError() {
            return "请求必须包含 user_id、case_id、player_json_file 或 player_json。";
        }
    } 
}
