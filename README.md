# Debugger Enhanced Code Completion

## Project Overview

This project aims to evaluate and improve code completion capabilities by incorporating debugging information such as stack traces and variable states into large language models (LLMs). The system will leverage debug-time context to generate more accurate and contextually appropriate code completions at the repository level.

### Research Objectives

- Determine if and how debugging information improves code completion accuracy
- Identify which types of debugging data provide the most value to LLMs
- Develop a methodology for effectively feeding debugging context to code completion models
- Create a practical implementation in the form of a VSCode extension
- Compare performance against baseline models without debugging and code completion systems (GitHub Copiler, Cursor) 

### Technical Objectives

Develop a VSCode extension that will be able to generate necessary code to pass defined unit tests.

Flow from the user perspective:
1. User selects a function signature and associated tests
2. System runs tests with debugging enabled to collect context information
3. Debug data is processed and combined with code context. Combined context is sent to LLM for code completion
4. Generated code is returned and presented to the user. User can accept, modify, or request refinements

## Experimentation Framework

### Debugging Information Subsets

The system will experiment with various combinations of debugging information:

- **Basic Information**
  - Function signature and docstring
  - Test cases
  
- **Static Context**
  - Repository structure
  - Imported modules
  - Referenced functions and classes
  
- **Dynamic Context**
  - Call stack at key points
  - Variable states before/during/after execution
  - Execution paths
  - Runtime values of function parameters
  - Exception information (if applicable)

### Interaction Modes

We plan to evaluate 2 ways to feed debugging information into the LLM:

 - **Batch Mode**. Collects all debugging information upfront and generates complete function in a single LLM call.

 - **Interactive Mode**. Model has full control over the debugging process. It can collect all the necessary data by stepping through the functions. 

## User Interface Specification

The VSCode extension will provide:

- A command palette option to initiate function completion
- Interface for selecting function signature and associated tests
- Visualization of debugging information being used
- Preview of generated code with syntax highlighting
- Options to accept, modify, or request refinement of the completion
- Performance metrics display (test pass rate, similarity to original, etc.)

## Evaluation Methodology

### Assumptions and Benchmark Dataset

To test our system we will need a set of well-covered projects. We will create a dataset from 10 open-source projects. For each project, a set of functions with comprehensive test coverage will be identified and removed. The system will attempt to regenerate these functions using only their signatures, associated tests, and various debugging information.

1. [Project 1]
2. [Project 2]
3. [Project 3]
4. [Project 4]
5. [Project 5]
6. [Project 6]
7. [Project 7]
8. [Project 8]
9. [Project 9]
10. [Project 10]

### Evaluation Metrics

- Functional Correctness: Percentage of tests passed
- Syntactic Similarity: Comparison to original implementation (using code similarity metrics)
- Execution Efficiency: Runtime and memory usage comparison
- Completion Time: Time required to generate valid code

## Project Timeline

### Phase 1: System Logic Development (March - April 2025)
- Design core architecture
- Implement debugging information collectors
- Develop context building strategies
- Run initial experiments to determine optimal debugging info subsets

### Phase 2: Proof of Concept (May 2025)
- Implement working VSCode extension
- Integrate with LLM providers
- Conduct baseline experiments
- Document initial findings

### Phase 3: Refinement and Extended Research (June - September 2025)
- Optimize context generation strategies
- Expand benchmark dataset
- Implement interactive refinement features
- Conduct comprehensive comparative evaluation
- Prepare final research documentation