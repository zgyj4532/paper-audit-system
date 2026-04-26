package com.auditor.engine.service.validators;

import com.auditor.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Reference Ordering Validator
 * 
 * Function: Check whether the references are arranged in the order they appear in the main text (sequential numbering system)
 * Rules:
 *   1. References should be arranged in the order they are cited in the main text
 *   2. Reference numbers should be continuous (no skipping numbers)
 * Severity: MEDIUM / HIGH
 */
@Component
public class ReferenceOrderingValidator {
    
    private static final Logger logger = LoggerFactory.getLogger(ReferenceOrderingValidator.class);
    private static final Pattern CITATION_PATTERN = Pattern.compile("\\[(\\d+)\\]");
    
    /**
     * Validate reference ordering
     * 
     * @param data Parsed document data
     * @return List of detected issues
     */
    public List<Issue> validateReferenceOrdering(ParsedData data) {
        List<Issue> issues = new ArrayList<>();
        
        if (data == null) {
            logger.warn("Input data is null");
            return issues;
        }
        
        try {
            // 1. Collect citations in the order they appear in the main text
            List<Integer> citationOrder = extractCitationOrder(data);
            logger.debug("Citation order in main text: {}", citationOrder);
            
            // 2. Extract citation order from references
            List<Integer> referenceOrder = extractReferenceOrder(data);
            logger.debug("Citation order in references: {}", referenceOrder);
            
            // 3. Check if arranged according to citation order
            checkOrderingConsistency(citationOrder, referenceOrder, issues);
            
            // 4. Check numbering continuity
            checkNumberingContinuity(referenceOrder, issues);
            
            logger.info("Reference ordering validation completed, found {} issues", issues.size());
            
        } catch (Exception e) {
            logger.error("Reference ordering validation exception", e);
            Issue errorIssue = Issue.newBuilder()
                    .setCode("ERR_REFERENCE_ORDER")
                    .setMessage("参考文献顺序校验异常：" + e.getMessage())
                    .setSeverity(Severity.HIGH)
                    .build();
            issues.add(errorIssue);
        }
        
        return issues;
    }
    
    /**
     * Extract citations in the order they appear in the main text
     */
    private List<Integer> extractCitationOrder(ParsedData data) {
        List<Integer> citationOrder = new ArrayList<>();
        Set<Integer> seen = new HashSet<>();
        
        for (Section section : data.getSectionsList()) {
            Matcher matcher = CITATION_PATTERN.matcher(section.getText());
            while (matcher.find()) {
                try {
                    int id = Integer.parseInt(matcher.group(1));
                    if (!seen.contains(id)) {
                        citationOrder.add(id);
                        seen.add(id);
                    }
                } catch (NumberFormatException e) {
                    logger.warn("Unable to parse citation ID: {}", matcher.group(1));
                }
            }
        }
        
        return citationOrder;
    }
    
    /**
     * Extract citation order from references
     */
    private List<Integer> extractReferenceOrder(ParsedData data) {
        List<Integer> referenceOrder = new ArrayList<>();
        
        for (Reference ref : data.getReferencesList()) {
            String refId = ref.getRefId(); // "[1]"
            try {
                int id = Integer.parseInt(refId.replaceAll("[\\[\\]]", ""));
                referenceOrder.add(id);
            } catch (NumberFormatException e) {
                logger.warn("Unable to parse reference ID: {}", refId);
            }
        }
        
        return referenceOrder;
    }
    
    /**
     * Check ordering consistency
     */
    private void checkOrderingConsistency(List<Integer> citationOrder, List<Integer> referenceOrder, List<Issue> issues) {
        if (citationOrder.isEmpty() || referenceOrder.isEmpty()) {
            return;
        }
        
        // Compare only existing citations
        List<Integer> expectedOrder = new ArrayList<>();
        for (Integer id : citationOrder) {
            if (referenceOrder.contains(id)) {
                expectedOrder.add(id);
            }
        }
        
        // Extract corresponding order from references
        List<Integer> actualOrder = new ArrayList<>();
        for (Integer id : referenceOrder) {
            if (expectedOrder.contains(id)) {
                actualOrder.add(id);
            }
        }
        
        if (!expectedOrder.equals(actualOrder)) {
            Issue issue = Issue.newBuilder()
                    .setCode("REF_ORDER_001")
                    .setMessage("参考文献顺序应与正文引用顺序一致")
                    .setSeverity(Severity.MEDIUM)
                    .setSuggestion("请按正文引用顺序重新排列参考文献")
                    .setOriginalSnippet("Expected order: " + expectedOrder + ", Actual order: " + actualOrder)
                    .build();
            issues.add(issue);
            logger.debug("Detected ordering inconsistency");
        }
    }
    
    /**
     * Check numbering continuity
     */
    private void checkNumberingContinuity(List<Integer> referenceOrder, List<Issue> issues) {
        if (referenceOrder.isEmpty()) {
            return;
        }
        
        for (int i = 0; i < referenceOrder.size(); i++) {
            int expectedId = i + 1;
            int actualId = referenceOrder.get(i);
            
            if (actualId != expectedId) {
                Issue issue = Issue.newBuilder()
                        .setCode("REF_ORDER_002")
                    .setMessage("参考文献编号不连续：期望为 [" + expectedId + " ]，实际为 [" + actualId + "]")
                        .setSeverity(Severity.HIGH)
                        .setSuggestion("请重新编号参考文献，确保编号从 1 开始且连续")
                        .build();
                issues.add(issue);
                logger.debug("Detected numbering discontinuity: expected [{}], actual [{}]", expectedId, actualId);
                break; // Report only the first discontinuity
            }
        }
    }
}