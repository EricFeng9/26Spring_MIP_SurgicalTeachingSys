package com.retinal.auth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public final class MultipartFormDataParser {
    private MultipartFormDataParser() {
    }

    public static Map<String, Part> parse(byte[] bodyBytes, String contentTypeHeader) throws IOException {
        String boundary = extractBoundary(contentTypeHeader);
        if (boundary == null || boundary.isBlank()) {
            throw new IOException("invalid multipart content-type: boundary is missing");
        }

        String raw = new String(bodyBytes, StandardCharsets.ISO_8859_1);
        String delimiter = "--" + boundary;
        String[] chunks = raw.split(Pattern.quote(delimiter));
        Map<String, Part> parts = new HashMap<>();

        for (String chunk : chunks) {
            if (chunk == null || chunk.isBlank()) {
                continue;
            }

            String normalized = chunk;
            if (normalized.startsWith("\r\n")) {
                normalized = normalized.substring(2);
            }
            if (normalized.equals("--") || normalized.equals("--\r\n")) {
                continue;
            }
            if (normalized.endsWith("\r\n")) {
                normalized = normalized.substring(0, normalized.length() - 2);
            }
            if (normalized.endsWith("--")) {
                normalized = normalized.substring(0, normalized.length() - 2);
                if (normalized.endsWith("\r\n")) {
                    normalized = normalized.substring(0, normalized.length() - 2);
                }
            }

            int split = normalized.indexOf("\r\n\r\n");
            if (split <= 0) {
                continue;
            }

            String headerText = normalized.substring(0, split);
            String bodyText = normalized.substring(split + 4);
            byte[] partBytes = bodyText.getBytes(StandardCharsets.ISO_8859_1);

            Part part = parsePart(headerText, partBytes);
            if (part != null && part.name() != null && !part.name().isBlank()) {
                parts.put(part.name(), part);
            }
        }

        return parts;
    }

    private static Part parsePart(String headerText, byte[] partBytes) {
        String[] lines = headerText.split("\r\n");
        String contentDisposition = null;
        String contentType = null;
        for (String line : lines) {
            String lower = line.toLowerCase(Locale.ROOT);
            if (lower.startsWith("content-disposition:")) {
                contentDisposition = line.substring("content-disposition:".length()).trim();
            } else if (lower.startsWith("content-type:")) {
                contentType = line.substring("content-type:".length()).trim();
            }
        }

        if (contentDisposition == null) {
            return null;
        }

        String name = extractQuotedParam(contentDisposition, "name");
        String filename = extractQuotedParam(contentDisposition, "filename");
        return new Part(name, filename, contentType, partBytes);
    }

    private static String extractQuotedParam(String headerValue, String key) {
        String token = key + "=\"";
        int start = headerValue.indexOf(token);
        if (start < 0) {
            return null;
        }
        int from = start + token.length();
        int end = headerValue.indexOf('"', from);
        if (end < 0) {
            return null;
        }
        return headerValue.substring(from, end);
    }

    private static String extractBoundary(String contentTypeHeader) {
        if (contentTypeHeader == null) {
            return null;
        }
        String[] segments = contentTypeHeader.split(";");
        for (String segment : segments) {
            String s = segment.trim();
            if (!s.startsWith("boundary=")) {
                continue;
            }
            String value = s.substring("boundary=".length()).trim();
            if (value.startsWith("\"") && value.endsWith("\"") && value.length() >= 2) {
                value = value.substring(1, value.length() - 1);
            }
            return value;
        }
        return null;
    }

    public record Part(
            String name,
            String fileName,
            String contentType,
            byte[] bytes
    ) {
        public String asUtf8Text() {
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }
}
