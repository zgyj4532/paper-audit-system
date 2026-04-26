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
 *   <li><b>Table Skip</b>: Sections whose type is table will be removed from the review list, because metadata tables do not need the full integrity/format/reference rule pass.</li>
 * </ol>
 *
 * <p>Typical scenario: The "学位论文数据集" paragraph should remain in the review list so numbering stays continuous,
 * while the following appendix metadata table should be skipped from rule review.
 */
@Service
public class SectionFilterService {

    private static final Logger logger = LoggerFactory.getLogger(SectionFilterService.class);

        /**
         * Stop detection keyword list.
         * Kept as a general text matcher for tests and other callers.
         */
        public static final List<String> STOP_KEYWORDS = Collections.unmodifiableList(Arrays.asList(
            "学位论文数据集"
        ));

    /**
    * Filters sections in {@link ParsedData} and returns a new {@link ParsedData},
    * whose sections list has been filtered according to table skipping rules.
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
        for (int i = 0; i < originalSections.size(); i++) {
            Section section = originalSections.get(i);
            String text = section.getText() == null ? "" : section.getText().trim();
            String type = section.getType() == null ? "" : section.getType().trim().toLowerCase();

            // Skip appendix/metadata tables before sending to rule engines.
            if ("table".equals(type)) {
                logger.debug("Table section skipped, section[{}] text='{}'", i, text);
                continue;
            }

            filteredSections.add(section);
        }

        // If no table sections were skipped, return original data directly
        if (filteredSections.size() == originalSections.size()) {
            logger.debug("Section filtering: no truncation, no table skip, returning original data");
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

}