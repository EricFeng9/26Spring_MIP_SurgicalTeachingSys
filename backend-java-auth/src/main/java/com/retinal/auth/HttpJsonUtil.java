package com.retinal.auth;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class HttpJsonUtil {
    private HttpJsonUtil() {
    }

    public static String readJsonString(String json, String key) {
        if (json == null || key == null || key.isEmpty()) {
            return null;
        }

        String patternText = "\\\"" + Pattern.quote(key) + "\\\"\\s*:\\s*\\\"((?:\\\\.|[^\\\"])*)\\\"";
        Pattern pattern = Pattern.compile(patternText);
        Matcher matcher = pattern.matcher(json);
        if (!matcher.find()) {
            return null;
        }

        return unescapeJson(matcher.group(1));
    }

    public static String buildAuthResultJson(AuthResult result) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"success\":").append(result.success());
        sb.append(",\"message\":\"").append(escapeJson(result.message())).append("\"");
        if (result.token() != null) {
            sb.append(",\"token\":\"").append(escapeJson(result.token())).append("\"");
        }
        sb.append("}");
        return sb.toString();
    }

    public static String buildErrorJson(String message) {
        return "{\"success\":false,\"message\":\"" + escapeJson(message) + "\"}";
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
                case '\b':
                    out.append("\\b");
                    break;
                case '\f':
                    out.append("\\f");
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
                    if (ch < 0x20) {
                        out.append(String.format("\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                    break;
            }
        }
        return out.toString();
    }

    private static String unescapeJson(String value) {
        StringBuilder out = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (ch != '\\' || i == value.length() - 1) {
                out.append(ch);
                continue;
            }

            char next = value.charAt(++i);
            switch (next) {
                case '"':
                    out.append('"');
                    break;
                case '\\':
                    out.append('\\');
                    break;
                case '/':
                    out.append('/');
                    break;
                case 'b':
                    out.append('\b');
                    break;
                case 'f':
                    out.append('\f');
                    break;
                case 'n':
                    out.append('\n');
                    break;
                case 'r':
                    out.append('\r');
                    break;
                case 't':
                    out.append('\t');
                    break;
                case 'u':
                    if (i + 4 < value.length()) {
                        String hex = value.substring(i + 1, i + 5);
                        out.append((char) Integer.parseInt(hex, 16));
                        i += 4;
                    }
                    break;
                default:
                    out.append(next);
                    break;
            }
        }

        return out.toString();
    }
}
