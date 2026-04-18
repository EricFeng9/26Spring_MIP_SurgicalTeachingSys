package com.retinal.auth;

public final class HttpJsonUtil {
    private HttpJsonUtil() {
    }

    public static String readJsonString(String json, String key) {
        if (json == null || key == null || key.isEmpty()) {
            return null;
        }

        int i = skipWhitespace(json, 0);
        if (i >= json.length() || json.charAt(i) != '{') {
            return null;
        }
        i++;

        while (i < json.length()) {
            i = skipWhitespace(json, i);
            if (i < json.length() && json.charAt(i) == '}') {
                return null;
            }

            ParseResult keyResult = parseJsonString(json, i);
            if (keyResult == null) {
                return null;
            }
            String parsedKey = keyResult.value;
            i = skipWhitespace(json, keyResult.nextIndex);
            if (i >= json.length() || json.charAt(i) != ':') {
                return null;
            }

            i = skipWhitespace(json, i + 1);
            if (key.equals(parsedKey)) {
                ParseResult valueResult = parseJsonString(json, i);
                return valueResult == null ? null : valueResult.value;
            }

            i = skipJsonValue(json, i);
            i = skipWhitespace(json, i);
            if (i < json.length() && json.charAt(i) == ',') {
                i++;
            }
        }

        return null;
    }

    public static String readJsonValueAsString(String json, String key) {
        if (json == null || key == null || key.isEmpty()) {
            return null;
        }

        int i = skipWhitespace(json, 0);
        if (i >= json.length() || json.charAt(i) != '{') {
            return null;
        }
        i++;

        while (i < json.length()) {
            i = skipWhitespace(json, i);
            if (i < json.length() && json.charAt(i) == '}') {
                return null;
            }

            ParseResult keyResult = parseJsonString(json, i);
            if (keyResult == null) {
                return null;
            }

            i = skipWhitespace(json, keyResult.nextIndex);
            if (i >= json.length() || json.charAt(i) != ':') {
                return null;
            }

            i = skipWhitespace(json, i + 1);
            if (key.equals(keyResult.value)) {
                if (i >= json.length()) {
                    return null;
                }

                if (json.charAt(i) == '"') {
                    ParseResult stringResult = parseJsonString(json, i);
                    return stringResult == null ? null : stringResult.value;
                }

                int end = skipJsonValue(json, i);
                if (end <= i) {
                    return null;
                }

                String raw = json.substring(i, end).trim();
                if (raw.isEmpty() || "null".equals(raw)) {
                    return null;
                }

                if (raw.startsWith("{") || raw.startsWith("[")) {
                    return null;
                }
                return raw;
            }

            i = skipJsonValue(json, i);
            i = skipWhitespace(json, i);
            if (i < json.length() && json.charAt(i) == ',') {
                i++;
            }
        }

        return null;
    }

    private static int skipWhitespace(String json, int i) {
        while (i < json.length() && Character.isWhitespace(json.charAt(i))) {
            i++;
        }
        return i;
    }

    private static int skipJsonValue(String json, int i) {
        if (i >= json.length()) {
            return i;
        }

        char ch = json.charAt(i);
        if (ch == '"') {
            ParseResult r = parseJsonString(json, i);
            return r == null ? json.length() : r.nextIndex;
        }

        if (ch == '{' || ch == '[') {
            char open = ch;
            char close = ch == '{' ? '}' : ']';
            int depth = 0;
            for (int p = i; p < json.length(); p++) {
                char c = json.charAt(p);
                if (c == '"') {
                    ParseResult r = parseJsonString(json, p);
                    if (r == null) {
                        return json.length();
                    }
                    p = r.nextIndex - 1;
                    continue;
                }
                if (c == open) {
                    depth++;
                } else if (c == close) {
                    depth--;
                    if (depth == 0) {
                        return p + 1;
                    }
                }
            }
            return json.length();
        }

        int p = i;
        while (p < json.length()) {
            char c = json.charAt(p);
            if (c == ',' || c == '}' || c == ']') {
                break;
            }
            p++;
        }
        return p;
    }

    private static ParseResult parseJsonString(String json, int start) {
        if (start >= json.length() || json.charAt(start) != '"') {
            return null;
        }

        StringBuilder out = new StringBuilder();
        int i = start + 1;
        while (i < json.length()) {
            char ch = json.charAt(i++);
            if (ch == '"') {
                return new ParseResult(out.toString(), i);
            }

            if (ch != '\\') {
                out.append(ch);
                continue;
            }

            if (i >= json.length()) {
                break;
            }

            char next = json.charAt(i++);
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
                    if (i + 4 <= json.length()) {
                        String hex = json.substring(i, i + 4);
                        try {
                            out.append((char) Integer.parseInt(hex, 16));
                            i += 4;
                        } catch (NumberFormatException ignored) {
                            out.append('u');
                        }
                    } else {
                        out.append('u');
                    }
                    break;
                default:
                    out.append(next);
                    break;
            }
        }

        return null;
    }

    private record ParseResult(String value, int nextIndex) {
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

}
