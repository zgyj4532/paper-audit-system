package rules.reference;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Reference rules helper class: extract citation numbers from the main text
 * Used by the original 26 reference.drl rules
 */
public class ExtractCitationNumbers {
    // Supports formats like [1], [1,2], [1-3], etc.
    private static final Pattern CITATION_PATTERN = Pattern.compile("\\[\\s*(\\d+(?:\\s*[-,\\s]\\s*\\d+)*)\\s*\\]");

    /**
     * Extract citation numbers
     * @param text input text
     * @return list of numbers
     */
    public static List<Integer> extractCitationNumbers(String text) {
        List<Integer> numbers = new ArrayList<>();
        if (text == null || text.isEmpty()) {
            return numbers;
        }
        Matcher matcher = CITATION_PATTERN.matcher(text);
        while (matcher.find()) {
            String group = matcher.group(1);
            String[] parts = group.split("[,\\s]+");
            for (String part : parts) {
                if (part.isEmpty()) continue;
                if (part.contains("-")) {
                    String[] range = part.split("-");
                    try {
                        int start = Integer.parseInt(range[0].trim());
                        int end = Integer.parseInt(range[1].trim());
                        for (int i = start; i <= end; i++) numbers.add(i);
                    } catch (Exception ignored) {}
                } else {
                    try {
                        numbers.add(Integer.parseInt(part.trim()));
                    } catch (Exception ignored) {}
                }
            }
        }
        return numbers;
    }
}