package com.auditor.engine.service;

import com.auditor.grpc.ParsedData;
import com.auditor.grpc.Section;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Section Pre-filtering Service
 *
 * <p>Before sending {@link ParsedData} into various rule engines, preprocess the sections list:
 * <ol>
 *   <li><b>Stop Detection (Truncation)</b>: When iterating through sections, once a section with <b>type=heading</b> 
 *       whose text contains any keyword in {@link #STOP_KEYWORDS} is encountered, immediately truncate — 
 *       this section and all subsequent sections will not participate in further review.
 *       Note: type=paragraph directory entries (e.g., "学位论文数据集\t25") do not trigger truncation to avoid mistakenly truncating the main text.</li>
 *   <li><b>Whitelist (Skip)</b>: Sections whose text is listed in {@link #WHITELIST_SECTION_TEXTS} will be removed from the review list even if they appear before the truncation point, producing no Issues.</li>
 * </ol>
 *
 * <p>Typical scenario: The "学位论文数据集" chapter on page 33 of Li Liangxun's thesis is an appendix metadata table,
 * which is not part of the main thesis text and should not be checked by formatting/integrity/reference rules.
 */
@Service
public class SectionFilterService {

    private static final Logger logger = LoggerFactory.getLogger(SectionFilterService.class);

    /**
     * Stop detection keyword list.
     * When a section with <b>type=heading</b> contains any of the following keywords,
     * that section and all subsequent sections will not enter the rule engine.
     * Directory entries with type=paragraph containing the same text do not trigger truncation.
     */
    public static final List<String> STOP_KEYWORDS = Collections.unmodifiableList(Arrays.asList(
            "学位论文数据集"
    ));

    /**
     * Whitelist section text list (exact match, ignoring leading and trailing whitespace).
     * Sections in the whitelist will be silently skipped and not sent to the rule engine even if they appear before the truncation point.
     */
    public static final List<String> WHITELIST_SECTION_TEXTS = Collections.unmodifiableList(Arrays.asList(
            "学位论文数据集",
            "独创性声明",
            "学位论文版权使用授权书",
            "版权声明"
    ));

    /**
     * Filters sections in {@link ParsedData} and returns a new {@link ParsedData},
     * whose sections list has been truncated/filtered according to stop detection and whitelist rules.
     * The original {@code data} object will not be modified (Protobuf objects are immutable).
     *
     * @param data Original parsed data
     * @return Filtered ParsedData; returns null as is if {@code data} is null
     */
    public ParsedData filterSections(ParsedData data) {
        if (data == null) {
            return null;
        }

        List<Section> originalSections = data.getSectionsList();
        if (originalSections.isEmpty()) {
            return data;
        }

        List<Section> filteredSections = new ArrayList<>();
        int stopIndex = -1;

        for (int i = 0; i < originalSections.size(); i++) {
            Section section = originalSections.get(i);
            String text = section.getText() == null ? "" : section.getText().trim();
            String type = section.getType() == null ? "" : section.getType();

            // 1. Check if stop keyword is triggered (higher priority than whitelist)
            //    Key constraint: only section titles with type=heading trigger truncation.
            //    Directory entries with type=paragraph (e.g., "学位论文数据集\t25") contain the keyword,
            //    but they are ordinary paragraphs on the directory page, not real section titles, and should not trigger truncation.
            if ("heading".equals(type) && matchesStopKeyword(text)) {
                stopIndex = i;
                logger.info("Detected stop keyword, section[{}] type=heading text='{}' — this section and the following {} sections will be skipped",
                        i, text, originalSections.size() - i);
                break;
            }

            // 2. Check if in whitelist (whitelisted sections are silently skipped and not added to review list)
            if (isWhitelisted(text)) {
                logger.debug("Whitelist hit, skipping section[{}] text='{}'", i, text);
                continue;
            }

            filteredSections.add(section);
        }

        // If no truncation and no whitelist hit, return original data directly
        if (stopIndex == -1 && filteredSections.size() == originalSections.size()) {
            logger.debug("Section filtering: no truncation, no whitelist hit, returning original data");
            return data;
        }

        int removedCount = originalSections.size() - filteredSections.size();
        logger.info("Section filtering completed: original {} sections, filtered {} sections, removed {} sections",
                originalSections.size(), filteredSections.size(), removedCount);

        // Build new ParsedData, only replacing the sections list
        ParsedData.Builder builder = data.toBuilder();
        builder.clearSections();
        builder.addAllSections(filteredSections);
        return builder.build();
    }

    /**
     * Determines whether the given text contains any stop keywords.
     */
    public boolean matchesStopKeyword(String text) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        for (String keyword : STOP_KEYWORDS) {
            if (text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Determines whether the given text is in the whitelist (exact match, ignoring leading and trailing whitespace).
     */
    public boolean isWhitelisted(String text) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        for (String whitelisted : WHITELIST_SECTION_TEXTS) {
            if (text.equals(whitelisted.trim())) {
                return true;
            }
        }
        return false;
    }
}