package io.github.koreatest12.codex.biff;

public final class PiiMasker {
    private PiiMasker() {}

    public static String mask(String kind, String value) {
        if (value == null) return "";
        String normalized = kind == null ? "other" : kind.trim().toLowerCase();
        String text = value.trim();

        return switch (normalized) {
            case "phone" -> maskPhone(text);
            case "email" -> maskEmail(text);
            case "contact" -> text.contains("@") ? maskEmail(text)
                    : text.chars().filter(Character::isDigit).count() >= 7
                    ? maskPhone(text) : maskExceptLast(text, 2);
            case "reservation", "other" -> maskExceptLast(text, 4);
            default -> throw new IllegalArgumentException("unsupported kind: " + kind);
        };
    }

    private static String maskExceptLast(String value, int visible) {
        if (value.isEmpty()) return "";
        int keep = Math.max(0, Math.min(visible, value.length()));
        return "*".repeat(value.length() - keep) + value.substring(value.length() - keep);
    }

    private static String maskPhone(String value) {
        int digitsToKeep = 4;
        int digitsSeen = 0;
        StringBuilder result = new StringBuilder(value.length());
        for (int i = value.length() - 1; i >= 0; i--) {
            char ch = value.charAt(i);
            if (Character.isDigit(ch)) {
                digitsSeen++;
                result.append(digitsSeen <= digitsToKeep ? ch : '*');
            } else {
                result.append(ch);
            }
        }
        return result.reverse().toString();
    }

    private static String maskEmail(String value) {
        int at = value.lastIndexOf('@');
        if (at < 0) return maskExceptLast(value, 2);
        String local = value.substring(0, at);
        String domain = value.substring(at + 1);
        int dot = domain.indexOf('.');
        String host = dot >= 0 ? domain.substring(0, dot) : domain;
        String suffix = dot >= 0 ? domain.substring(dot) : "";
        String maskedLocal = (local.isEmpty() ? "" : local.substring(0, 1)) + "***";
        String maskedHost = (host.isEmpty() ? "" : host.substring(0, 1)) + "***";
        return maskedLocal + "@" + maskedHost + suffix;
    }
}
