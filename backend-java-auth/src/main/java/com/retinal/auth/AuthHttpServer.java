package com.retinal.auth;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

public final class AuthHttpServer {
    private final HttpServer server;
    private final AuthService authService;
    private final CaseService caseService;

    public AuthHttpServer(int port, AuthService authService) throws IOException {
        this.server = HttpServer.create(new InetSocketAddress(port), 0);
        this.authService = authService;
        this.caseService = new CaseService();
        registerRoutes();
    }

    public static AuthHttpServer createDefault(int port) throws SQLException, IOException {
        DatabaseManager db = DatabaseManager.fromEnv();
        db.initialize();
        return new AuthHttpServer(port, new AuthService(db));
    }

    public void start() {
        server.start();
        System.out.println("Auth API listening on http://localhost:" + server.getAddress().getPort());
    }

    public void stop(int delaySeconds) {
        server.stop(delaySeconds);
    }

    private void registerRoutes() {
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

        server.createContext("/api/cases", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }

            String caseId = extractCaseId(exchange);
            if (caseId == null || caseId.isBlank()) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("缺少 caseId。请使用 /api/cases/{caseId}"));
                return;
            }

            String caseJson = caseService.getCaseDetailJson(caseId);
            if (caseJson == null) {
                writeJson(exchange, 404, HttpJsonUtil.buildErrorJson("关卡不存在: " + caseId));
                return;
            }

            writeJson(exchange, 200, caseJson);
        });

        // 图片访问接口: /api/assets/images/{caseId}/{preop|postop_2w}
        server.createContext("/api/assets/images", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                writeMethodNotAllowed(exchange);
                return;
            }

            String[] imageRequest = extractCaseImageRequest(exchange);
            if (imageRequest == null) {
                writeJson(exchange, 400, HttpJsonUtil.buildErrorJson("请使用 /api/assets/images/{caseId}/{preop|postop_2w}"));
                return;
            }

            CaseService.ImageFile imageFile = caseService.getCaseImage(imageRequest[0], imageRequest[1]);
            if (imageFile == null) {
                writeJson(exchange, 404, HttpJsonUtil.buildErrorJson("图片不存在或配置错误: " + imageRequest[0] + "/" + imageRequest[1]));
                return;
            }

            writeBinary(exchange, 200, imageFile.contentType(), imageFile.bytes());
        });
    }

    private static String extractCaseId(HttpExchange exchange) {
        String path = exchange.getRequestURI().getPath();
        String prefix = "/api/cases/";
        if (path != null && path.startsWith(prefix) && path.length() > prefix.length()) {
            return path.substring(prefix.length());
        }
        return null;
    }

    private static String[] extractCaseImageRequest(HttpExchange exchange) {
        String path = exchange.getRequestURI().getPath();
        String prefix = "/api/assets/images/";
        if (path == null || !path.startsWith(prefix) || path.length() <= prefix.length()) {
            return null;
        }

        String remain = path.substring(prefix.length());
        String[] parts = remain.split("/");
        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            return null;
        }

        return new String[] { parts[0], parts[1] };
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
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    private static void writeBinary(HttpExchange exchange, int statusCode, String contentType, byte[] bytes) throws IOException {
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", contentType != null ? contentType : "application/octet-stream");
        headers.set("Access-Control-Allow-Origin", "*");
        headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
        headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");

        exchange.sendResponseHeaders(statusCode, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
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
