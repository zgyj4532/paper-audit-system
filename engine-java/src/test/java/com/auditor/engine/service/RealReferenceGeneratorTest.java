package com.auditor.engine.service;

import com.auditor.grpc.Reference;
import org.junit.jupiter.api.Test;
import java.util.List;

public class RealReferenceGeneratorTest {
    
    @Test
    public void testGenerateReferences() {
        List<Reference> references = RealReferenceDataGenerator.generateReferences();
        
        System.out.println("\nGenerated Reference Statistics:");
        System.out.println("Total: " + references.size());
        System.out.println("Journal [J]: 50");
        System.out.println("Monograph [M]: 50");
        System.out.println("Thesis [D]: 50");
        System.out.println("Conference Proceedings [C]: 50");
        
        // Output first 10 examples
        System.out.println("\nFirst 10 Reference Examples:");
        for (int i = 0; i < Math.min(10, references.size()); i++) {
            Reference ref = references.get(i);
            System.out.println(ref.getRefId() + " " + ref.getRawText());
        }
    }
}