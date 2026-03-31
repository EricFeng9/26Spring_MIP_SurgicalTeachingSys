package com.retinal.auth;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

public final class DatabaseManager {
    private final String jdbcUrl;
    private final String username;
    private final String password;

    public DatabaseManager(String host, int port, String databaseName, String username, String password) {
        this.jdbcUrl = "jdbc:postgresql://" + host + ":" + port + "/" + databaseName;
        this.username = username;
        this.password = password;
        ensureDriverLoaded();
    }

    public Connection getConnection() throws SQLException {
        return DriverManager.getConnection(jdbcUrl, username, password);
    }

    public void initialize() throws SQLException {
        try (Connection conn = getConnection(); Statement stmt = conn.createStatement()) {
            stmt.executeUpdate(
                    "CREATE TABLE IF NOT EXISTS players ("
                            + "id BIGSERIAL PRIMARY KEY,"
                            + "username VARCHAR(64) NOT NULL UNIQUE,"
                            + "password_hash VARCHAR(128) NOT NULL,"
                            + "salt VARCHAR(64) NOT NULL,"
                            + "created_at VARCHAR(64) NOT NULL,"
                            + "last_login_at VARCHAR(64) NULL"
                            + ");");

            stmt.executeUpdate(
                    "CREATE TABLE IF NOT EXISTS sessions ("
                            + "token VARCHAR(128) PRIMARY KEY,"
                            + "username VARCHAR(64) NOT NULL,"
                            + "login_at VARCHAR(64) NOT NULL,"
                            + "logout_at VARCHAR(64) NULL,"
                            + "active SMALLINT NOT NULL,"
                            + "FOREIGN KEY(username) REFERENCES players(username)"
                            + ");");
        }
    }

    public static DatabaseManager fromEnv() {
        String host = envOrDefault("DB_HOST", "127.0.0.1");
        int port = Integer.parseInt(envOrDefault("DB_PORT", "5432"));
        String database = envOrDefault("DB_NAME", "retinal_auth");
        String user = envOrDefault("DB_USER", "postgres");
        String pass = envOrDefault("DB_PASSWORD", "postgres");
        return new DatabaseManager(host, port, database, user, pass);
    }

    private static String envOrDefault(String key, String defaultValue) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            return defaultValue;
        }
        return value.trim();
    }

    private static void ensureDriverLoaded() {
        try {
            Class.forName("org.postgresql.Driver");
        } catch (ClassNotFoundException e) {
            throw new IllegalStateException("Missing postgresql driver in classpath", e);
        }
    }
}
