package rules.reference;

/**
 * Reference rule helper class: extract numbers from the reference list
 * Called by the original 26 reference.drl rules
 */
public class ExtractReferenceNumber {
    
    /**
     * Extract numeric number from reference ID
     * @param refId Reference ID (e.g. "[1]")
     * @return Integer number
     */
    public static int extractReferenceNumber(String refId) {
        if (refId == null || refId.isEmpty()) {
            return 0;
        }
        try {
            // Remove brackets and parse as integer
            String cleaned = refId.replaceAll("\\[|\\]", "").trim();
            return Integer.parseInt(cleaned);
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}