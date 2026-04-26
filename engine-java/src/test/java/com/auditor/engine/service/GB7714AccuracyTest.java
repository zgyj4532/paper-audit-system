package com.auditor.engine.service;

import com.auditor.grpc.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * GB/T 7714 Reference Accuracy Self-Test
 * Contains 20 deliberately incorrect references
 * Requires Drools to detect all, otherwise report error
 */
public class GB7714AccuracyTest {

    private ReferenceChecker referenceChecker;

    @BeforeEach
    public void setUp() {
        referenceChecker = new ReferenceChecker();
    }

    @Test
    public void testGB7714Accuracy() {
        // Construct 20 deliberately incorrect references
        ParsedData data = buildTestData();

        // Run check
        List<Issue> issues = referenceChecker.checkReferences(data);

        // Print all detected issues
        System.out.println("\n========== GB/T 7714 Accuracy Self-Test Results ==========");
        System.out.println("Total detected issues: " + issues.size());
        System.out.println();

        for (Issue issue : issues) {
            System.out.println("✗ [" + issue.getCode() + "] " + issue.getMessage());
        }

        // Verify number of detected issues
        // Expect at least 20 issues detected (at least 1 issue per incorrect reference)
        assertTrue(issues.size() >= 20, 
                "Accuracy self-test failed: detected issues " + issues.size() + " < 20, indicating Drools rules missed detections");

        System.out.println("\n✅ Accuracy self-test passed! Detected " + issues.size() + " issues");
    }

    private ParsedData buildTestData() {
        ParsedData.Builder builder = ParsedData.newBuilder()
                .setDocId("accuracy-test")
                .setMetadata(DocumentMetadata.newBuilder()
                        .setTitle("GB/T 7714 Accuracy Self-Test")
                        .setPageCount(1)
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(1)
                        .setLevel(1)
                        .setType("heading")
                        .setText("References")
                        .build())
                .addSections(Section.newBuilder()
                        .setSectionId(2)
                        .setLevel(0)
                        .setType("paragraph")
                        .setText("According to studies [1-20]...")
                        .build());

        // Error 1: Journal reference, uses full-width comma
        builder.addReferences(Reference.newBuilder()
                .setRefId("[1]")
                .setRawText("[1] 张三，李四. 论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                .build());

        // Error 2: Journal reference, year exceeds 2026
        builder.addReferences(Reference.newBuilder()
                .setRefId("[2]")
                .setRawText("[2] 张三, 李四. 论文题名[J]. 期刊名, 2027, 10(2): 1-10.")
                .build());

        // Error 3: Journal reference, missing period after [J]
        builder.addReferences(Reference.newBuilder()
                .setRefId("[3]")
                .setRawText("[3] 张三, 李四. 论文题名[J] 期刊名, 2023, 10(2): 1-10.")
                .build());

        // Error 4: Journal reference, missing volume(issue)
        builder.addReferences(Reference.newBuilder()
                .setRefId("[4]")
                .setRawText("[4] 张三, 李四. 论文题名[J]. 期刊名, 2023, 1-10.")
                .build());

        // Error 5: Journal reference, missing page numbers
        builder.addReferences(Reference.newBuilder()
                .setRefId("[5]")
                .setRawText("[5] 张三, 李四. 论文题名[J]. 期刊名, 2023, 10(2).")
                .build());

        // Error 6: Journal reference, multiple authors but missing "et al."
        builder.addReferences(Reference.newBuilder()
                .setRefId("[6]")
                .setRawText("[6] 张三, 李四, 王五, 赵六. 论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                .build());

        // Error 7: Monograph reference, uses full-width period
        builder.addReferences(Reference.newBuilder()
                .setRefId("[7]")
                .setRawText("[7] 张三。 书名[M]。 北京: 出版社, 2023.")
                .build());

        // Error 8: Monograph reference, year exceeds 2026
        builder.addReferences(Reference.newBuilder()
                .setRefId("[8]")
                .setRawText("[8] 张三. 书名[M]. 北京: 出版社, 2030.")
                .build());

        // Error 9: Monograph reference, missing period after [M]
        builder.addReferences(Reference.newBuilder()
                .setRefId("[9]")
                .setRawText("[9] 张三. 书名[M] 北京: 出版社, 2023.")
                .build());

        // Error 10: Monograph reference, missing place of publication: publisher
        builder.addReferences(Reference.newBuilder()
                .setRefId("[10]")
                .setRawText("[10] 张三. 书名[M]. 2023.")
                .build());

        // Error 11: Journal reference, uses full-width semicolon
        builder.addReferences(Reference.newBuilder()
                .setRefId("[11]")
                .setRawText("[11] 张三, 李四. 论文题名[J]；期刊名, 2023, 10(2): 1-10.")
                .build());

        // Error 12: Monograph reference, multiple authors but missing "et al."
        builder.addReferences(Reference.newBuilder()
                .setRefId("[12]")
                .setRawText("[12] 张三, 李四, 王五, 赵六. 书名[M]. 北京: 出版社, 2023.")
                .build());

        // Error 13: Journal reference, year is two digits
        builder.addReferences(Reference.newBuilder()
                .setRefId("[13]")
                .setRawText("[13] 张三, 李四. 论文题名[J]. 期刊名, 23, 10(2): 1-10.")
                .build());

        // Error 14: Journal reference, year too early (< 1900)
        builder.addReferences(Reference.newBuilder()
                .setRefId("[14]")
                .setRawText("[14] 张三, 李四. 论文题名[J]. 期刊名, 1800, 10(2): 1-10.")
                .build());

        // Error 15: Monograph reference, year is two digits
        builder.addReferences(Reference.newBuilder()
                .setRefId("[15]")
                .setRawText("[15] 张三. 书名[M]. 北京: 出版社, 99.")
                .build());

        // Error 16: Journal reference, mixed Chinese and English punctuation
        builder.addReferences(Reference.newBuilder()
                .setRefId("[16]")
                .setRawText("[16] 张三, 李四。论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                .build());

        // Error 17: Monograph reference, mixed Chinese and English punctuation
        builder.addReferences(Reference.newBuilder()
                .setRefId("[17]")
                .setRawText("[17] 张三。 书名[M]. 北京: 出版社, 2023.")
                .build());

        // Error 18: Journal reference, missing author
        builder.addReferences(Reference.newBuilder()
                .setRefId("[18]")
                .setRawText("[18] 论文题名[J]. 期刊名, 2023, 10(2): 1-10.")
                .build());

        // Error 19: Monograph reference, missing author
        builder.addReferences(Reference.newBuilder()
                .setRefId("[19]")
                .setRawText("[19] 书名[M]. 北京: 出版社, 2023.")
                .build());

        // Error 20: Journal reference, incorrect [J] tag (should be uppercase)
        builder.addReferences(Reference.newBuilder()
                .setRefId("[20]")
                .setRawText("[20] 张三, 李四. 论文题名[j]. 期刊名, 2023, 10(2): 1-10.")
                .build());

        return builder.build();
    }
}