package com.retinal.auth;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.UUID;

public final class AuthService {
    private final DatabaseManager db;

    public AuthService(DatabaseManager db) {
        this.db = db;
    }

    public AuthResult register(String username, String password) {
        String normalized = normalizeUsername(username);
        if (!isValidUsername(normalized)) {
            return AuthResult.fail("用户名需为3-20位，仅允许小写字母、数字和下划线。");
        }
        if (!isValidPassword(password)) {
            return AuthResult.fail("密码至少6位。");
        }

        String checkSql = "SELECT 1 FROM players WHERE username = ?";
        String insertSql = "INSERT INTO players(username, password_hash, salt, created_at) VALUES(?,?,?,?)";

        try (Connection conn = db.getConnection();
             PreparedStatement checkStmt = conn.prepareStatement(checkSql);
             PreparedStatement insertStmt = conn.prepareStatement(insertSql)) {

            checkStmt.setString(1, normalized);
            try (ResultSet rs = checkStmt.executeQuery()) {
                if (rs.next()) {
                    return AuthResult.fail("该用户名已存在。");
                }
            }

            String salt = PasswordUtil.newSalt();
            String hash = PasswordUtil.hash(password, salt);
            insertStmt.setString(1, normalized);
            insertStmt.setString(2, hash);
            insertStmt.setString(3, salt);
            insertStmt.setString(4, Instant.now().toString());
            insertStmt.executeUpdate();

            return AuthResult.ok("注册成功。");
        } catch (SQLException e) {
            return AuthResult.fail("注册失败: " + e.getMessage());
        }
    }

    public AuthResult login(String username, String password) {
        String normalized = normalizeUsername(username);
        if (!isValidUsername(normalized)) {
            return AuthResult.fail("用户名格式不正确。");
        }
        if (!isValidPassword(password)) {
            return AuthResult.fail("密码格式不正确。");
        }

        String querySql = "SELECT password_hash, salt FROM players WHERE username = ?";
        String updateSql = "UPDATE players SET last_login_at = ? WHERE username = ?";
        String sessionSql = "INSERT INTO sessions(token, username, login_at, active) VALUES(?,?,?,1)";

        try (Connection conn = db.getConnection();
             PreparedStatement queryStmt = conn.prepareStatement(querySql);
             PreparedStatement updateStmt = conn.prepareStatement(updateSql);
             PreparedStatement sessionStmt = conn.prepareStatement(sessionSql)) {

            queryStmt.setString(1, normalized);
            String expectedHash;
            String salt;

            try (ResultSet rs = queryStmt.executeQuery()) {
                if (!rs.next()) {
                    return AuthResult.fail("账号不存在。");
                }
                expectedHash = rs.getString("password_hash");
                salt = rs.getString("salt");
            }

            String incomingHash = PasswordUtil.hash(password, salt);
            if (!expectedHash.equals(incomingHash)) {
                return AuthResult.fail("密码错误。");
            }

            String now = Instant.now().toString();
            updateStmt.setString(1, now);
            updateStmt.setString(2, normalized);
            updateStmt.executeUpdate();

            String token = UUID.randomUUID().toString();
            sessionStmt.setString(1, token);
            sessionStmt.setString(2, normalized);
            sessionStmt.setString(3, now);
            sessionStmt.executeUpdate();

            return AuthResult.okWithToken("登录成功。", token);
        } catch (SQLException e) {
            return AuthResult.fail("登录失败: " + e.getMessage());
        }
    }

    public AuthResult logout(String token) {
        if (token == null || token.isBlank()) {
            return AuthResult.fail("token 不能为空。");
        }

        String sql = "UPDATE sessions SET active = 0, logout_at = ? WHERE token = ? AND active = 1";
        try (Connection conn = db.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setString(1, Instant.now().toString());
            stmt.setString(2, token.trim());
            int updated = stmt.executeUpdate();
            if (updated == 0) {
                return AuthResult.fail("登出失败: 会话不存在或已失效。");
            }
            return AuthResult.ok("登出成功。");
        } catch (SQLException e) {
            return AuthResult.fail("登出失败: " + e.getMessage());
        }
    }

    private static String normalizeUsername(String username) {
        if (username == null) {
            return "";
        }
        return username.trim().toLowerCase();
    }

    private static boolean isValidUsername(String username) {
        if (username.length() < 3 || username.length() > 20) {
            return false;
        }
        for (int i = 0; i < username.length(); i++) {
            char c = username.charAt(i);
            boolean isLower = c >= 'a' && c <= 'z';
            boolean isDigit = c >= '0' && c <= '9';
            if (!(isLower || isDigit || c == '_')) {
                return false;
            }
        }
        return true;
    }

    private static boolean isValidPassword(String password) {
        return password != null && password.length() >= 6;
    }
}
