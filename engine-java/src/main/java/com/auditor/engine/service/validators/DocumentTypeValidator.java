package com.auditor.engine.service.validators;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Document Type Validator
 * 
 * Function: Check if required fields are complete based on document type
 * Supported document types:
 *   - thesis: Academic thesis
 *   - journal: Journal article
 *   - conference: Conference paper
 *   - book: Monograph
 */
@Component
public class DocumentTypeValidator {
    
    private static final Logger logger = LoggerFactory.getLogger(DocumentTypeValidator.class);
    
    // Define required fields for different document types
    private static final Map<String, String[]> REQUIRED_FIELDS = new HashMap<>();
    
    static {
        // Thesis: requires degree, school, advisor, etc.
        REQUIRED_FIELDS.put("thesis", new String[]{
            "title", "author", "school", "advisor", "year", "degree", "abstract"
        });
        
        // Journal article: requires journal name, volume, issue, pages, etc.
        REQUIRED_FIELDS.put("journal", new String[]{
            "title", "author", "journal", "volume", "issue", "pages", "year", "doi"
        });
        
        // Conference paper: requires conference name, location, date, etc.
        REQUIRED_FIELDS.put("conference", new String[]{
            "title", "author", "conference", "location", "date", "pages", "year"
        });
        
        // Monograph: requires edition, print count, etc.
        REQUIRED_FIELDS.put("book", new String[]{
            "title", "author", "publisher", "year", "edition", "isbn"
        });
    }
    
    /**
     * Validate document type and required fields
     * 
     * @param data Parsed document data
     * @return List of found issues
     */
    public List<Issue> validateDocumentType(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null || !data.hasMetadata()) {
            logger.warn("Input data is null or missing metadata");
            return issues;
        }
        
        try {
            DocumentMetadata metadata = data.getMetadata();
            
            // Infer document type from title field (since proto has no documentType field)
            String title = metadata.getTitle();
            String docType = inferDocumentType(title);
            
            logger.debug("Inferred document type: {}", docType);
            
            // Check if document type is supported
            if (!REQUIRED_FIELDS.containsKey(docType)) {
                Issue issue = Issue.newBuilder()
                        .setCode("INT_TYPE_UNKNOWN")
                    .setMessage("未知的文档类型：" + docType)
                        .setSeverity(Severity.MEDIUM)
                    .setSuggestion("请指定有效的文档类型：thesis、journal、conference、book")
                        .build();
                issues.add(issue);
                logger.warn("Unknown document type: {}", docType);
                return issues;
            }
            
            // Check basic required fields
            if (title.isEmpty()) {
                Issue issue = Issue.newBuilder()
                        .setCode("INT_TYPE_MISSING_TITLE")
                    .setMessage("文档缺少标题")
                        .setSeverity(Severity.HIGH)
                    .setSuggestion("请补充文档标题")
                        .build();
                issues.add(issue);
            }
            
            if (metadata.getPageCount() <= 0) {
                Issue issue = Issue.newBuilder()
                        .setCode("INT_TYPE_MISSING_PAGES")
                    .setMessage("文档页数无效")
                        .setSeverity(Severity.MEDIUM)
                    .setSuggestion("请确保文档页数有效")
                        .build();
                issues.add(issue);
            }
            
            // Perform additional checks based on document type
            checkDocumentTypeSpecificRules(docType, metadata, issues);
            
            logger.info("Document type validation completed, found {} issues", issues.size());
            
        } catch (Exception e) {
            logger.error("Document type validation exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_TYPE_VALIDATION")
                    .setMessage("文档类型校验异常：" + e.getMessage())
                    .setSeverity(Severity.HIGH)
                    .build();
            issues.add(errorIssue);
        }
        
        return issues;
    }
    
    /**
     * Infer document type from title
     */
    private String inferDocumentType(String title) {
        if (title.isEmpty()) {
            return "unknown";
        }
        
        String lowerTitle = title.toLowerCase();
        
        if (lowerTitle.contains("学位论文") || lowerTitle.contains("thesis") || 
            lowerTitle.contains("dissertation")) {
            return "thesis";
        } else if (lowerTitle.contains("期刊") || lowerTitle.contains("journal") ||
                   lowerTitle.contains("article")) {
            return "journal";
        } else if (lowerTitle.contains("会议") || lowerTitle.contains("conference") ||
                   lowerTitle.contains("proceedings")) {
            return "conference";
        } else if (lowerTitle.contains("专著") || lowerTitle.contains("book")) {
            return "book";
        }
        
        return "thesis"; // Default to thesis
    }
    
    /**
     * Perform additional checks based on document type
     */
    private void checkDocumentTypeSpecificRules(String docType, DocumentMetadata metadata, List<Issue> issues) {
        switch (docType) {
            case "thesis":
                checkThesisSpecificRules(metadata, issues);
                break;
            case "journal":
                checkJournalSpecificRules(metadata, issues);
                break;
            case "conference":
                checkConferenceSpecificRules(metadata, issues);
                break;
            case "book":
                checkBookSpecificRules(metadata, issues);
                break;
        }
    }
    
    /**
     * Thesis specific rules
     */
    private void checkThesisSpecificRules(DocumentMetadata metadata, List<Issue> issues) {
        // Thesis should have sufficient pages
        if (metadata.getPageCount() < 20) {
            Issue issue = Issue.newBuilder()
                    .setCode("INT_THESIS_PAGES")
                    .setMessage("学位论文页数过少，通常应不少于 20 页")
                    .setSeverity(Severity.MEDIUM)
                    .setSuggestion("请补充论文内容")
                    .build();
            issues.add(issue);
        }
    }
    
    /**
     * Journal article specific rules
     */
    private void checkJournalSpecificRules(DocumentMetadata metadata, List<Issue> issues) {
        // Journal articles are usually shorter
        if (metadata.getPageCount() > 50) {
            Issue issue = Issue.newBuilder()
                    .setCode("INT_JOURNAL_PAGES_LONG")
                    .setMessage("期刊文章页数较多，请确认文档类型是否为期刊文章")
                    .setSeverity(Severity.LOW)
                    .setSuggestion("请检查文档类型是否正确")
                    .build();
            issues.add(issue);
        }
    }
    
    /**
     * Conference paper specific rules
     */
    private void checkConferenceSpecificRules(DocumentMetadata metadata, List<Issue> issues) {
        // Conference papers are usually 4-8 pages
        if (metadata.getPageCount() < 4) {
            Issue issue = Issue.newBuilder()
                    .setCode("INT_CONF_PAGES_SHORT")
                    .setMessage("会议论文页数过少，通常为 4-8 页")
                    .setSeverity(Severity.LOW)
                    .setSuggestion("请检查文档是否完整")
                    .build();
            issues.add(issue);
        }
    }
    
    /**
     * Monograph specific rules
     */
    private void checkBookSpecificRules(DocumentMetadata metadata, List<Issue> issues) {
        // Monographs are usually thick
        if (metadata.getPageCount() < 50) {
            Issue issue = Issue.newBuilder()
                    .setCode("INT_BOOK_PAGES_SHORT")
                    .setMessage("专著页数过少，通常应超过 50 页")
                    .setSeverity(Severity.LOW)
                    .setSuggestion("请检查文档是否完整")
                    .build();
            issues.add(issue);
        }
    }
}