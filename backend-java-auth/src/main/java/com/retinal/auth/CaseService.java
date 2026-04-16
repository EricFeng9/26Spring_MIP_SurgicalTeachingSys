package com.retinal.auth;

import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public final class CaseService {
    private final Path casesDirectory;

    public static final class ImageFile {
        private final byte[] bytes;
        private final String contentType;

        public ImageFile(byte[] bytes, String contentType) {
            this.bytes = bytes;
            this.contentType = contentType;
        }

        public byte[] bytes() {
            return bytes;
        }

        public String contentType() {
            return contentType;
        }
    }

    public CaseService() {
        // 设置存放 JSON 文件的目录为项目根目录下的 data/cases
        this.casesDirectory = Paths.get("data", "cases");
        // 确保目录存在
        try {
            if (!Files.exists(this.casesDirectory)) {
                Files.createDirectories(this.casesDirectory);
            }
        } catch (IOException e) {
            System.err.println("Failed to create cases directory: " + e.getMessage());
        }
    }

    public String getCaseDetailJson(String caseId) {
        String safeCaseId = sanitizeCaseId(caseId);
        if (safeCaseId.isEmpty()) {
            return null;
        }

        Path caseFile = resolveCaseJsonPath(safeCaseId);
        if (caseFile == null) {
            return null;
        }

        if (Files.exists(caseFile) && Files.isRegularFile(caseFile)) {
            try {
                return Files.readString(caseFile, StandardCharsets.UTF_8);
            } catch (IOException e) {
                System.err.println("Error reading case file " + caseFile + ": " + e.getMessage());
                return null;
            }
        }

        return null;
    }

    public ImageFile getCaseImage(String caseId, String imageType) {
        String safeCaseId = sanitizeCaseId(caseId);
        if (safeCaseId.isEmpty()) {
            return null;
        }

        String imageField;
        if ("preop".equalsIgnoreCase(imageType)) {
            imageField = "preop_image_path";
        } else if ("postop_2w".equalsIgnoreCase(imageType)) {
            imageField = "postop_2w_image_path";
        } else {
            return null;
        }

        Path caseFile = resolveCaseJsonPath(safeCaseId);
        if (caseFile == null) {
            return null;
        }

        try {
            String caseJson = Files.readString(caseFile, StandardCharsets.UTF_8);
            String imagePathText = HttpJsonUtil.readJsonString(caseJson, imageField);
            if (imagePathText == null || imagePathText.isBlank()) {
                return null;
            }

            String imageRef = imagePathText.trim();
            if (isHttpUrl(imageRef)) {
                return loadRemoteImage(imageRef);
            }

            Path caseDir = caseFile.getParent();
            Path rawPath = Paths.get(imageRef);
            Path resolvedPath = rawPath.isAbsolute() ? rawPath : caseDir.resolve(rawPath).normalize();

            // 相对路径仅允许在当前病例目录下，防止目录穿越
            if (!rawPath.isAbsolute() && !resolvedPath.startsWith(caseDir.normalize())) {
                return null;
            }

            if (!Files.exists(resolvedPath) || !Files.isRegularFile(resolvedPath)) {
                return null;
            }

            byte[] bytes = Files.readAllBytes(resolvedPath);
            String contentType = Files.probeContentType(resolvedPath);
            if (contentType == null) {
                String lower = resolvedPath.getFileName().toString().toLowerCase();
                if (lower.endsWith(".png")) {
                    contentType = "image/png";
                } else if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
                    contentType = "image/jpeg";
                } else if (lower.endsWith(".webp")) {
                    contentType = "image/webp";
                } else {
                    contentType = "application/octet-stream";
                }
            }

            return new ImageFile(bytes, contentType);
        } catch (IOException e) {
            System.err.println("Error loading case image for " + safeCaseId + ": " + e.getMessage());
            return null;
        }
    }

    private static boolean isHttpUrl(String text) {
        if (text == null) {
            return false;
        }
        String lower = text.toLowerCase();
        return lower.startsWith("http://") || lower.startsWith("https://");
    }

    private ImageFile loadRemoteImage(String imageUrl) {
        HttpURLConnection connection = null;
        try {
            String normalizedUrl = normalizeRemoteUrl(imageUrl);
            if (normalizedUrl == null) {
                return null;
            }

            URL url = new URL(normalizedUrl);
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(10000);
            connection.setInstanceFollowRedirects(true);

            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                return null;
            }

            byte[] bytes;
            try (InputStream in = connection.getInputStream()) {
                bytes = in.readAllBytes();
            }

            String contentType = connection.getContentType();
            if (contentType == null || contentType.isBlank()) {
                String lower = imageUrl.toLowerCase();
                if (lower.endsWith(".png")) {
                    contentType = "image/png";
                } else if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
                    contentType = "image/jpeg";
                } else if (lower.endsWith(".webp")) {
                    contentType = "image/webp";
                } else {
                    contentType = "application/octet-stream";
                }
            }

            return new ImageFile(bytes, contentType);
        } catch (IOException e) {
            System.err.println("Error loading remote image " + imageUrl + ": " + e.getMessage());
            return null;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static String normalizeRemoteUrl(String imageUrl) {
        if (imageUrl == null || imageUrl.isBlank()) {
            return null;
        }

        String raw = imageUrl.trim().replace(" ", "%20");
        try {
            URI uri = URI.create(raw);
            if (uri.getScheme() == null || uri.getHost() == null) {
                return null;
            }
            return uri.toASCIIString();
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private Path resolveCaseJsonPath(String safeCaseId) {
        Path nestedCaseFile = casesDirectory.resolve(safeCaseId).resolve(safeCaseId + ".json");
        if (Files.exists(nestedCaseFile) && Files.isRegularFile(nestedCaseFile)) {
            return nestedCaseFile;
        }

        Path flatCaseFile = casesDirectory.resolve(safeCaseId + ".json");
        if (Files.exists(flatCaseFile) && Files.isRegularFile(flatCaseFile)) {
            return flatCaseFile;
        }

        return null;
    }

    private static String sanitizeCaseId(String caseId) {
        if (caseId == null) {
            return "";
        }
        return caseId.trim().replaceAll("[^a-zA-Z0-9_\\-]", "");
    }
}
