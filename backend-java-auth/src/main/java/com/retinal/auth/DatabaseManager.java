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

                        stmt.executeUpdate(
                            "CREATE TABLE IF NOT EXISTS levels ("
                                + "id BIGSERIAL PRIMARY KEY,"
                                + "level_code VARCHAR(64) NOT NULL UNIQUE,"
                                + "name VARCHAR(128) NOT NULL,"
                                + "difficulty VARCHAR(32) NOT NULL DEFAULT 'normal',"
                                + "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                                + ");");

                        stmt.executeUpdate(
                            "CREATE TABLE IF NOT EXISTS image_versions ("
                                + "id BIGSERIAL PRIMARY KEY,"
                                + "level_id BIGINT NOT NULL,"
                                + "version_tag VARCHAR(64) NOT NULL,"
                                + "image_uri TEXT NOT NULL,"
                                + "answer_key_json JSONB NULL,"
                                + "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
                                + "UNIQUE(level_id, version_tag),"
                                + "FOREIGN KEY(level_id) REFERENCES levels(id)"
                                + ");");

                        stmt.executeUpdate(
                            "CREATE TABLE IF NOT EXISTS play_sessions ("
                                + "id BIGSERIAL PRIMARY KEY,"
                                + "session_uuid VARCHAR(64) NOT NULL UNIQUE,"
                                + "username VARCHAR(64) NOT NULL,"
                                + "level_id BIGINT NOT NULL,"
                                + "image_version_id BIGINT NOT NULL,"
                                + "status VARCHAR(16) NOT NULL DEFAULT 'in_progress',"
                                + "started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
                                + "submitted_at TIMESTAMPTZ NULL,"
                                + "duration_ms BIGINT NULL,"
                                + "FOREIGN KEY(username) REFERENCES players(username),"
                                + "FOREIGN KEY(level_id) REFERENCES levels(id),"
                                + "FOREIGN KEY(image_version_id) REFERENCES image_versions(id)"
                                + ");");

                        stmt.executeUpdate(
                            "CREATE TABLE IF NOT EXISTS action_events ("
                                + "id BIGSERIAL PRIMARY KEY,"
                                + "session_id BIGINT NOT NULL,"
                                + "event_seq INTEGER NOT NULL,"
                                + "event_type VARCHAR(16) NOT NULL,"
                                + "x DOUBLE PRECISION NOT NULL,"
                                + "y DOUBLE PRECISION NOT NULL,"
                                + "event_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
                                + "zoom_scale DOUBLE PRECISION NULL,"
                                + "viewport_offset_x DOUBLE PRECISION NULL,"
                                + "viewport_offset_y DOUBLE PRECISION NULL,"
                                + "meta_json JSONB NULL,"
                                + "UNIQUE(session_id, event_seq),"
                                + "FOREIGN KEY(session_id) REFERENCES play_sessions(id) ON DELETE CASCADE"
                                + ");");

                        stmt.executeUpdate(
                            "CREATE TABLE IF NOT EXISTS score_reports ("
                                + "id BIGSERIAL PRIMARY KEY,"
                                + "session_id BIGINT NOT NULL UNIQUE,"
                                + "score_version VARCHAR(32) NOT NULL DEFAULT 'v1',"
                                + "total_score DOUBLE PRECISION NOT NULL,"
                                + "precision_score DOUBLE PRECISION NULL,"
                                + "recall_score DOUBLE PRECISION NULL,"
                                + "f1_score DOUBLE PRECISION NULL,"
                                + "miss_count INTEGER NOT NULL DEFAULT 0,"
                                + "false_positive_count INTEGER NOT NULL DEFAULT 0,"
                                + "avg_offset_px DOUBLE PRECISION NULL,"
                                + "report_json JSONB NOT NULL,"
                                + "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
                                + "FOREIGN KEY(session_id) REFERENCES play_sessions(id) ON DELETE CASCADE"
                                + ");");

                        stmt.executeUpdate("CREATE INDEX IF NOT EXISTS idx_play_sessions_username ON play_sessions(username);");
                        stmt.executeUpdate("CREATE INDEX IF NOT EXISTS idx_play_sessions_level ON play_sessions(level_id);");
                        stmt.executeUpdate("CREATE INDEX IF NOT EXISTS idx_events_session ON action_events(session_id);");
                        stmt.executeUpdate("CREATE INDEX IF NOT EXISTS idx_events_ts ON action_events(event_ts);");
        }
    }

    public static DatabaseManager fromEnv() {
        String host = envOrDefault("DB_HOST", "127.0.0.1");
        int port = Integer.parseInt(envOrDefault("DB_PORT", "5432"));
        String database = envOrDefault("DB_NAME", "retinal_auth");
        String user = envOrDefault("DB_USER", "postgres");
        // password:Zenith3101
        String pass = envOrDefault("DB_PASSWORD", "Zenith3101");
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
