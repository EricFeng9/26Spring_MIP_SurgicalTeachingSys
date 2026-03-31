package com.retinal.auth;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;

public final class AuthHttpServer {
    private final HttpServer server;
    private final AuthService authService;

    public AuthHttpServer(int port, AuthService authService) throws IOException {
        this.server = HttpServer.create(new InetSocketAddress(port), 0);
        this.authService = authService;
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
