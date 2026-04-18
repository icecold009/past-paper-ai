# 9618 AS Level Computer Science Practice Paper Generation Prompt

You are generating a CAIE 9618 AS Level Computer Science practice paper from extracted and segmented past-paper data.

## Syllabus Reference
- 2026 syllabus (Version 1, September 2023)
- AS Level covers sections 1–12 only (sections 13–20 are A Level only)

## AS Level Paper Structure
| Paper | Title                                  | Duration       | Marks | Questions        | Weight (AS) |
|-------|----------------------------------------|----------------|-------|------------------|-------------|
| P1    | Theory Fundamentals                    | 1 hr 30 min    | 75    | All compulsory   | 50%         |
| P2    | Fundamental Problem-solving & Programming Skills | 2 hrs | 75    | All compulsory   | 50%         |

## Blueprint Scaffold
### Paper 1 (Theory Fundamentals) — 75 marks
Covers: Sections 1–8 (Information Representation, Communication, Hardware, Processor Fundamentals, System Software, Security & Data Integrity, Ethics & Ownership, Databases)
- Typical: 8–10 questions, mix of short-answer and structured
- Approx. marks per question: 2–12 marks

### Paper 2 (Problem-solving & Programming) — 75 marks
Covers: Sections 9–12 (Algorithm Design, Data Types & Structures, Programming, Software Development)
- Candidates write answers in pseudocode (CAIE standard pseudocode)
- Typical: 3–5 multi-part questions
- Approx. marks per question: 8–20 marks

## Representative Examples
### Paper 1
- Example 1 (P1): Describe two differences between SRAM and DRAM. [4]
- Example 2 (P1): A bitmap image has a resolution of 640 × 480 pixels with a colour depth of 24 bits. Calculate the file size in megabytes before compression. Show your working. [3]
- Example 3 (P1): Explain the role of the Program Counter (PC) register during the Fetch stage of the Fetch-Execute cycle. [2]
- Example 4 (P1): State two advantages of using a star topology over a bus topology in a LAN. [2]
- Example 5 (P1): A relational database has two tables: Customer(CustomerID, Name, Email) and Order(OrderID, CustomerID, Date, Total). Write an SQL SELECT statement to retrieve the Name and Total for all orders placed by customers with a Total greater than 500. [4]

### Paper 2
- Example 1 (P2): Write pseudocode for a procedure that uses a linear search to find a target value in a 1D array of integers. The procedure should output the index if found, or a message if not found. [6]
- Example 2 (P2): Describe what is meant by a stack and give one example of its use in a computer system. Write pseudocode to implement a PUSH operation on a stack stored as an array. [5]
- Example 3 (P2): A program reads student marks from a text file, calculates the average, and outputs students who scored below the average. Write pseudocode for this program. [8]
- Example 4 (P2): Explain the difference between black-box testing and white-box testing. State one type of test data used in each. [4]

## Pseudocode Standard
Follow CAIE 9618 pseudocode conventions:
- Declarations: DECLARE x : INTEGER
- Assignment: x ← 5
- Selection: IF...THEN...ELSE...ENDIF
- Iteration: FOR...TO...NEXT, WHILE...DO...ENDWHILE, REPEAT...UNTIL
- Arrays: DECLARE arr : ARRAY[1:10] OF INTEGER
- Procedures/Functions: PROCEDURE name(param : TYPE) ... ENDPROCEDURE

## Output Requirements
- Produce one full draft practice paper (P1 and P2).
- P1 total = 75 marks; P2 total = 75 marks.
- All questions must be drawn from AS Level sections 1–12 only.
- Provide mark allocation per question/sub-question.
- Include a range of question types: define, describe, explain, calculate, construct, write pseudocode.
- Avoid copying any one past question verbatim.

<!-- AUTO-DATA-START -->
## Data-Driven Addendum (Auto-Generated)

Use this block as additional evidence from extracted data. Keep all subject-specific syllabus constraints from the handcrafted prompt above.

### Blueprint Scaffold Snapshot
- P1: target 2 questions, 75 total marks
- P2: target 2 questions, 75 total marks

### Representative Examples From Extracted Data
- Representative examples are currently mock placeholders. Add real PDFs and rerun extraction to populate subject-authentic examples.
<!-- AUTO-DATA-END -->
