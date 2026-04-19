package com.auditor.engine.statemachine;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Document State Machine
 * 
 * Function: Manage various states and transitions of documents in the audit process
 */
@Component
public class DocumentStateMachine {
    
    private static final Logger logger = LoggerFactory.getLogger(DocumentStateMachine.class);
    
    public enum DocumentState {
        INITIAL("Initial State"),
        PARSING("Parsing"),
        PARSED("Parsing Completed"),
        AUDITING("Auditing"),
        AUDIT_COMPLETE("Audit Completed"),
        FAILED("Failed"),
        ARCHIVED("Archived");
        
        private final String description;
        
        DocumentState(String description) {
            this.description = description;
        }
        
        public String getDescription() {
            return description;
        }
    }
    
    private String documentId = "default-doc";
    private DocumentState currentState = DocumentState.INITIAL;
    
    /**
     * Default constructor for Spring usage
     */
    public DocumentStateMachine() {
        logger.info("Initializing global document state machine");
    }
    
    public DocumentStateMachine(String documentId) {
        this.documentId = documentId;
        logger.info("Creating document state machine: {}", documentId);
    }
    
    public DocumentState getCurrentState() {
        return currentState;
    }
    
    public void transition(DocumentState nextState) {
        this.currentState = nextState;
        logger.info("Document {} state transitioned to: {}", documentId, nextState.getDescription());
    }
}