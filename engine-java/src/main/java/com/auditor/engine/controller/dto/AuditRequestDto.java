package com.auditor.engine.controller.dto;

import com.auditor.grpc.DocumentMetadata;
import com.auditor.grpc.ParsedData;
import com.auditor.grpc.Reference;
import com.auditor.grpc.Section;

import java.util.List;
import java.util.Map;

public record AuditRequestDto(
        String docId,
        String targetRuleSet,
        DocumentMetadataDto metadata,
        List<SectionDto> sections,
        List<ReferenceDto> references
) {
    public ParsedData toParsedData() {
        ParsedData.Builder builder = ParsedData.newBuilder();

        if (docId != null) {
            builder.setDocId(docId);
        }
        if (metadata != null) {
            builder.setMetadata(metadata.toProto());
        }
        if (sections != null) {
            for (SectionDto section : sections) {
                builder.addSections(section.toProto());
            }
        }
        if (references != null) {
            for (ReferenceDto reference : references) {
                builder.addReferences(reference.toProto());
            }
        }

        return builder.build();
    }

    public record DocumentMetadataDto(
            String title,
            Integer pageCount,
            Float marginTop,
            Float marginBottom
    ) {
        private DocumentMetadata toProto() {
            DocumentMetadata.Builder builder = DocumentMetadata.newBuilder();
            if (title != null) {
                builder.setTitle(title);
            }
            if (pageCount != null) {
                builder.setPageCount(pageCount);
            }
            if (marginTop != null) {
                builder.setMarginTop(marginTop);
            }
            if (marginBottom != null) {
                builder.setMarginBottom(marginBottom);
            }
            return builder.build();
        }
    }

    public record SectionDto(
            Integer sectionId,
            String type,
            Integer level,
            String text,
            Map<String, String> props
    ) {
        private Section toProto() {
            Section.Builder builder = Section.newBuilder();
            if (sectionId != null) {
                builder.setSectionId(sectionId);
            }
            if (type != null) {
                builder.setType(type);
            }
            if (level != null) {
                builder.setLevel(level);
            }
            if (text != null) {
                builder.setText(text);
            }
            if (props != null) {
                builder.putAllProps(props);
            }
            return builder.build();
        }
    }

    public record ReferenceDto(
            String refId,
            String rawText,
            Boolean isValidFormat
    ) {
        private Reference toProto() {
            Reference.Builder builder = Reference.newBuilder();
            if (refId != null) {
                builder.setRefId(refId);
            }
            if (rawText != null) {
                builder.setRawText(rawText);
            }
            if (isValidFormat != null) {
                builder.setIsValidFormat(isValidFormat);
            }
            return builder.build();
        }
    }
}