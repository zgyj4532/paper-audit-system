package com.auditor.engine.service;

import com.auditor.grpc.Reference;
import java.util.*;

/**
 * Real diversified reference data generator
 * Includes four types: [J], [M], [D], [C]
 * Each reference contains 1-3 random errors
 */
public class RealReferenceDataGenerator {
    
    private static final Random random = new Random(42); // Fixed seed for reproducibility
    
    // Real journal names
    private static final String[] JOURNALS = {
        "中国学术期刊网络出版总库",
        "计算机学报",
        "软件学报",
        "中国科学：信息科学",
        "自动化学报",
        "电子学报",
        "通信学报",
        "信息与控制",
        "系统工程理论与实践",
        "数据库学报",
        "IEEE Transactions on Software Engineering",
        "ACM Computing Surveys",
        "Journal of Machine Learning Research",
        "Nature Machine Intelligence",
        "Science Advances"
    };
    
    // Real publishers
    private static final String[] PUBLISHERS = {
        "清华大学出版社",
        "机械工业出版社",
        "电子工业出版社",
        "人民邮电出版社",
        "科学出版社",
        "高等教育出版社",
        "中国计算机学会",
        "Springer",
        "ACM Press",
        "IEEE Press"
    };
    
    // Chinese authors
    private static final String[] CN_AUTHORS = {
        "张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十",
        "刘明", "陈浩", "杨洋", "黄金", "何平", "罗军", "高峰", "林涛"
    };
    
    // English authors
    private static final String[] EN_AUTHORS = {
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
        "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas"
    };
    
    // Error type enumeration
    enum ErrorType {
        FULL_COMMA,           // Full-width comma
        FULL_PERIOD,          // Full-width period
        YEAR_EXCEED,          // Year out of range
        YEAR_EARLY,           // Year too early
        YEAR_TWO_DIGIT,       // Two-digit year
        NO_DOT_AFTER_TYPE,    // No dot after [J]
        NO_AUTHOR,            // Missing author
        NO_VOLUME,            // Missing volume number
        NO_PAGE,              // Missing page number
        NO_PUBLISHER,         // Missing publisher
        MULTI_AUTHOR_NO_ET,   // Multiple authors without "et al."
        LOWERCASE_TYPE        // Lowercase type marker
    }
    
    /**
     * Generate 200 real diversified references
     */
    public static List<Reference> generateReferences() {
        List<Reference> references = new ArrayList<>();
        
        int journalCount = 50;   // [J] Journals
        int monoCount = 50;      // [M] Monographs
        int thesisCount = 50;    // [D] Theses
        int confCount = 50;      // [C] Conference proceedings
        
        int id = 1;
        
        // Generate journal references
        for (int i = 0; i < journalCount; i++) {
            references.add(generateJournalReference(id++));
        }
        
        // Generate monographs
        for (int i = 0; i < monoCount; i++) {
            references.add(generateMonographReference(id++));
        }
        
        // Generate theses
        for (int i = 0; i < thesisCount; i++) {
            references.add(generateThesisReference(id++));
        }
        
        // Generate conference proceedings
        for (int i = 0; i < confCount; i++) {
            references.add(generateConferenceReference(id++));
        }
        
        return references;
    }
    
    /**
     * Generate journal reference [J]
     */
    private static Reference generateJournalReference(int id) {
        Set<ErrorType> errors = selectRandomErrors();
        
        String author = generateAuthors(random.nextInt(3) + 1, errors.contains(ErrorType.NO_AUTHOR));
        String title = "论文题名";
        String journal = JOURNALS[random.nextInt(JOURNALS.length)];
        int year = generateYear(errors);
        int volume = random.nextInt(50) + 1;
        int issue = random.nextInt(12) + 1;
        int startPage = random.nextInt(900) + 1;
        int endPage = startPage + random.nextInt(50) + 1;
        
        StringBuilder sb = new StringBuilder();
        sb.append("[").append(id).append("] ");
        sb.append(author).append(". ");
        sb.append(title);
        
        // Handle [J] marker
        if (errors.contains(ErrorType.NO_DOT_AFTER_TYPE)) {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[j]");
            } else {
                sb.append("[J]");
            }
        } else {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[j].");
            } else {
                sb.append("[J].");
            }
        }
        
        sb.append(" ");
        sb.append(journal);
        
        // Handle comma
        if (errors.contains(ErrorType.FULL_COMMA)) {
            sb.append("，");
        } else {
            sb.append(", ");
        }
        
        sb.append(year);
        
        // Handle volume number
        if (!errors.contains(ErrorType.NO_VOLUME)) {
            sb.append(", ").append(volume);
            sb.append("(").append(issue).append(")");
        }
        
        // Handle page numbers
        if (!errors.contains(ErrorType.NO_PAGE)) {
            sb.append(": ").append(startPage).append("-").append(endPage);
        }
        
        // Handle period
        if (errors.contains(ErrorType.FULL_PERIOD)) {
            sb.append("。");
        } else {
            sb.append(".");
        }
        
        return Reference.newBuilder()
                .setRefId("[" + id + "]")
                .setRawText(sb.toString())
                .build();
    }
    
    /**
     * Generate monograph [M]
     */
    private static Reference generateMonographReference(int id) {
        Set<ErrorType> errors = selectRandomErrors();
        
        String author = generateAuthors(random.nextInt(3) + 1, errors.contains(ErrorType.NO_AUTHOR));
        String title = "书名";
        String city = "北京";
        String publisher = PUBLISHERS[random.nextInt(PUBLISHERS.length)];
        int year = generateYear(errors);
        
        StringBuilder sb = new StringBuilder();
        sb.append("[").append(id).append("] ");
        sb.append(author).append(". ");
        sb.append(title);
        
        // Handle [M] marker
        if (errors.contains(ErrorType.NO_DOT_AFTER_TYPE)) {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[m]");
            } else {
                sb.append("[M]");
            }
        } else {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[m].");
            } else {
                sb.append("[M].");
            }
        }
        
        sb.append(" ");
        
        // Handle place of publication and publisher
        if (!errors.contains(ErrorType.NO_PUBLISHER)) {
            sb.append(city).append(": ").append(publisher);
        }
        
        sb.append(", ").append(year);
        
        // Handle period
        if (errors.contains(ErrorType.FULL_PERIOD)) {
            sb.append("。");
        } else {
            sb.append(".");
        }
        
        return Reference.newBuilder()
                .setRefId("[" + id + "]")
                .setRawText(sb.toString())
                .build();
    }
    
    /**
     * Generate thesis [D]
     */
    private static Reference generateThesisReference(int id) {
        Set<ErrorType> errors = selectRandomErrors();
        
        String author = generateAuthors(1, errors.contains(ErrorType.NO_AUTHOR));
        String title = "学位论文题名";
        String degree = "博士学位论文";
        String university = "清华大学";
        int year = generateYear(errors);
        
        StringBuilder sb = new StringBuilder();
        sb.append("[").append(id).append("] ");
        sb.append(author).append(". ");
        sb.append(title);
        
        // Handle [D] marker
        if (errors.contains(ErrorType.NO_DOT_AFTER_TYPE)) {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[d]");
            } else {
                sb.append("[D]");
            }
        } else {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[d].");
            } else {
                sb.append("[D].");
            }
        }
        
        sb.append(" ");
        sb.append(degree).append(", ");
        sb.append(university).append(", ");
        sb.append(year);
        
        // Handle period
        if (errors.contains(ErrorType.FULL_PERIOD)) {
            sb.append("。");
        } else {
            sb.append(".");
        }
        
        return Reference.newBuilder()
                .setRefId("[" + id + "]")
                .setRawText(sb.toString())
                .build();
    }
    
    /**
     * Generate conference proceedings [C]
     */
    private static Reference generateConferenceReference(int id) {
        Set<ErrorType> errors = selectRandomErrors();
        
        String author = generateAuthors(random.nextInt(3) + 1, errors.contains(ErrorType.NO_AUTHOR));
        String title = "会议论文题名";
        String conference = "第" + (random.nextInt(20) + 1) + "届国际会议";
        String city = "北京";
        int year = generateYear(errors);
        
        StringBuilder sb = new StringBuilder();
        sb.append("[").append(id).append("] ");
        sb.append(author).append(". ");
        sb.append(title);
        
        // Handle [C] marker
        if (errors.contains(ErrorType.NO_DOT_AFTER_TYPE)) {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[c]");
            } else {
                sb.append("[C]");
            }
        } else {
            if (errors.contains(ErrorType.LOWERCASE_TYPE)) {
                sb.append("[c].");
            } else {
                sb.append("[C].");
            }
        }
        
        sb.append(" ");
        sb.append(conference);
        
        // Handle comma
        if (errors.contains(ErrorType.FULL_COMMA)) {
            sb.append("，");
        } else {
            sb.append(", ");
        }
        
        sb.append(city).append(", ");
        sb.append(year);
        
        // Handle period
        if (errors.contains(ErrorType.FULL_PERIOD)) {
            sb.append("。");
        } else {
            sb.append(".");
        }
        
        return Reference.newBuilder()
                .setRefId("[" + id + "]")
                .setRawText(sb.toString())
                .build();
    }
    
    /**
     * Randomly select 1-3 errors
     */
    private static Set<ErrorType> selectRandomErrors() {
        Set<ErrorType> errors = new HashSet<>();
        int errorCount = random.nextInt(3) + 1; // 1-3 errors
        
        ErrorType[] allErrors = ErrorType.values();
        List<ErrorType> errorList = Arrays.asList(allErrors);
        Collections.shuffle(errorList, random);
        
        for (int i = 0; i < Math.min(errorCount, errorList.size()); i++) {
            errors.add(errorList.get(i));
        }
        
        return errors;
    }
    
    /**
     * Generate author names
     */
    private static String generateAuthors(int count, boolean noAuthor) {
        if (noAuthor) {
            return "";
        }
        
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < count; i++) {
            if (i > 0) {
                sb.append(", ");
            }
            
            if (random.nextBoolean()) {
                // Chinese author
                sb.append(CN_AUTHORS[random.nextInt(CN_AUTHORS.length)]);
            } else {
                // English author
                sb.append(EN_AUTHORS[random.nextInt(EN_AUTHORS.length)]);
            }
        }
        
        // Add "et al." for multiple authors
        if (count > 1 && random.nextBoolean()) {
            sb.append("等");
        }
        
        return sb.toString();
    }
    
    /**
     * Generate year (may contain errors)
     */
    private static int generateYear(Set<ErrorType> errors) {
        if (errors.contains(ErrorType.YEAR_EXCEED)) {
            return 2027; // Out of range
        } else if (errors.contains(ErrorType.YEAR_EARLY)) {
            return 1800 + random.nextInt(50); // Too early
        } else if (errors.contains(ErrorType.YEAR_TWO_DIGIT)) {
            return 20 + random.nextInt(10); // Two-digit year
        } else {
            return 2000 + random.nextInt(26); // Normal year
        }
    }
    
    /**
     * Generate builder code format
     */
    public static String generateBuilderCode() {
        List<Reference> references = generateReferences();
        StringBuilder code = new StringBuilder();
        
        code.append("// Generate 200 real diversified references\n");
        code.append("ParsedData.Builder dataBuilder = ParsedData.newBuilder();\n\n");
        
        for (Reference ref : references) {
            code.append("dataBuilder.addReferences(Reference.newBuilder()\n");
            code.append("    .setRefId(\"" + ref.getRefId() + "\")\n");
            code.append("    .setRawText(\"" + escapeString(ref.getRawText()) + "\")\n");
            code.append("    .build());\n\n");
        }
        
        code.append("ParsedData data = dataBuilder.build();\n");
        
        return code.toString();
    }
    
    /**
     * Escape special characters in string
     */
    private static String escapeString(String str) {
        return str.replace("\\", "\\\\")
                  .replace("\"", "\\\"")
                  .replace("\n", "\\n")
                  .replace("\r", "\\r");
    }
    
    public static void main(String[] args) {
        List<Reference> references = generateReferences();
        
        System.out.println("Generated reference statistics:");
        System.out.println("Total: " + references.size());
        System.out.println("Journals [J]: 50");
        System.out.println("Monographs [M]: 50");
        System.out.println("Theses [D]: 50");
        System.out.println("Conference proceedings [C]: 50");
        
        // Output first 5 examples
        System.out.println("\nFirst 5 reference examples:");
        for (int i = 0; i < Math.min(5, references.size()); i++) {
            Reference ref = references.get(i);
            System.out.println(ref.getRefId() + " " + ref.getRawText());
        }
    }
}