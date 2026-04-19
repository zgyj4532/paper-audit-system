package com.auditor.engine.controller;

import com.auditor.engine.controller.dto.AuditRequestDto;
import com.auditor.engine.controller.dto.AuditResponseDto;
import com.auditor.engine.service.DocumentAuditService;
import com.auditor.grpc.AuditResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/rules")
public class AuditController {

    private static final Logger logger = LoggerFactory.getLogger(AuditController.class);

    private final DocumentAuditService documentAuditService;

    public AuditController(DocumentAuditService documentAuditService) {
        this.documentAuditService = documentAuditService;
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {
        logger.info("Health check requested for /api/v1/rules/health");
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "ok");
        body.put("service", "engine-java");
        body.put("timestamp", Instant.now().toString());
        body.put("http_port", System.getenv().getOrDefault("ENGINE_JAVA_HTTP_PORT", "8081"));
        body.put("grpc_port", System.getenv().getOrDefault("ENGINE_JAVA_GRPC_PORT", "9191"));
        return ResponseEntity.ok(body);
    }

    @PostMapping(value = "/audit", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<AuditResponseDto> audit(@RequestBody AuditRequestDto request) {
        if (request == null) {
            logger.warn("Received null audit request body at /api/v1/rules/audit");
            return ResponseEntity.badRequest().body(AuditResponseDto.error("Request body cannot be null"));
        }

        logger.info(
                "Received audit request at /api/v1/rules/audit, docId={}, targetRuleSet={}, sections={}, references={}",
                request.docId(),
                request.targetRuleSet(),
                request.sections() == null ? 0 : request.sections().size(),
                request.references() == null ? 0 : request.references().size()
        );

        AuditResponse response = documentAuditService.audit(request.toParsedData(), request.targetRuleSet());
        AuditResponseDto dto = AuditResponseDto.fromProto(
                request.docId(),
                request.targetRuleSet(),
                response
        );
        logger.info(
                "Completed audit request at /api/v1/rules/audit, docId={}, issueCount={}, scoreImpact={}",
                request.docId(),
                dto.issues() == null ? 0 : dto.issues().size(),
                dto.scoreImpact()
        );
        return ResponseEntity.ok(dto);
    }
}