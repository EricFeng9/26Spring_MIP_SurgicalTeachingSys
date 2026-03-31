package com.retinal.auth;

public final class AuthResult {
    private final boolean success;
    private final String message;
    private final String token;

    public AuthResult(boolean success, String message, String token) {
        this.success = success;
        this.message = message;
        this.token = token;
    }

    public boolean success() {
        return success;
    }

    public String message() {
        return message;
    }

    public String token() {
        return token;
    }

    public static AuthResult ok(String message) {
        return new AuthResult(true, message, null);
    }

    public static AuthResult okWithToken(String message, String token) {
        return new AuthResult(true, message, token);
    }

    public static AuthResult fail(String message) {
        return new AuthResult(false, message, null);
    }
}
