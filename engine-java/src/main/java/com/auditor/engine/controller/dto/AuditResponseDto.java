package com.auditor.engine.controller.dto;

import com.auditor.grpc.AuditResponse;
import com.auditor.grpc.Issue;

import java.util.List;
import java.util.stream.Collectors;

public record AuditResponseDto(
        String status,
        String docId,
        String targetRuleSet,
        String ruleEngine,
        List<IssueDto> issues,
        float scoreImpact,
        SummaryDto summary
) {
    public static AuditResponseDto fromProto(String docId, String targetRuleSet, AuditResponse response) {
        List<IssueDto> issues = response.getIssuesList().stream()
                .map(IssueDto::fromProto)
                .collect(Collectors.toList());

        SummaryDto summary = new SummaryDto(
                issues.size(),
                (int) issues.stream().filter(issue -> "HIGH".equals(issue.severity()) || "CRITICAL".equals(issue.severity())).count(),
                (int) issues.stream().filter(issue -> "MEDIUM".equals(issue.severity())).count(),
                (int) issues.stream().filter(issue -> "LOW".equals(issue.severity())).count()
        );

        return new AuditResponseDto(
                "ok",
                docId,
                targetRuleSet,
                "drools",
                issues,
                response.getScoreImpact(),
                summary
        );
    }

    public static AuditResponseDto error(String message) {
        return new AuditResponseDto(
                "error",
                null,
                null,
                "drools",
                List.of(new IssueDto("ERR_HTTP_REQUEST", message, null, "HIGH", "", "")),
                0.0f,
                new SummaryDto(1, 1, 0, 0)
        );
    }

    public record IssueDto(
            String code,
            String message,
            Integer sectionId,
            String severity,
            String suggestion,
            String originalSnippet
    ) {
        public static IssueDto fromProto(Issue issue) {
            Integer sectionId = issue.getSectionId() == 0 ? null : issue.getSectionId();
            return new IssueDto(
                    issue.getCode(),
                    issue.getMessage(),
                    sectionId,
                    issue.getSeverity().name(),
                    issue.getSuggestion(),
                    issue.getOriginalSnippet()
            );
        }
    }

    public record SummaryDto(
            int issueCount,
            int highRiskCount,
            int mediumRiskCount,
            int lowRiskCount
    ) {
    }
}