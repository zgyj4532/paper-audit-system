package com.auditor.engine.grpc;

import com.auditor.engine.service.DocumentAuditService;
import com.auditor.grpc.*;
import io.grpc.stub.StreamObserver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Member B (Java): gRPC service implementation for executing formatting and rule audits
 */
public class DocumentAuditorServiceImpl extends com.auditor.grpc.DocumentAuditorGrpc.DocumentAuditorImplBase {

    private static final Logger logger = LoggerFactory.getLogger(DocumentAuditorServiceImpl.class);
    private final DocumentAuditService documentAuditService = new DocumentAuditService();

    @Override
    public void auditRules(AuditRequest request, StreamObserver<AuditResponse> responseObserver) {
        try {
            ParsedData data = request.getData();
            String targetRuleSet = request.getTargetRuleSet();
            logger.info("Received audit request, Document ID: {}, Target rule set: {}", data.getDocId(), targetRuleSet);

            AuditResponse response = documentAuditService.audit(data, targetRuleSet);
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (Exception e) {
            logger.error("Audit execution error: {}", e.getMessage(), e);
            responseObserver.onError(io.grpc.Status.INTERNAL
                    .withDescription("Audit execution error: " + e.getMessage())
                    .asRuntimeException());
        }
    }
}