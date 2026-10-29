# HW8 AI-use disclosure

## 1. What AI helped with and what the student supplied

The user supplied the assignment, demos, fixed configuration, execution plan and
direction to extend the semester application. The AI coordinator inspected the
baseline, set shared contracts, delegated two isolated implementation units,
integrated their code, ran local experiments and drafted the report. The subagents
implemented Parts 1 and 2 and focused tests. This run does not claim the student
independently wrote or manually verified work they have not reviewed.

## 2. One unsuitable AI output or independently checked result

The initial AI-written harness stopped recovered Writer after observing output,
before its successful commit acknowledgment was captured. That was unsuitable
for proving commit timing. Runtime inspection also found Kafka writing outside
the volume mounted by Compose.

## 3. How the issue was found

The objective verifier checked actual offset_committed events and failed the first
recovery evidence. Inspecting the running broker configuration showed the actual
log directory differed from the mount. These checks used real runtime evidence.

## 4. What changed and why it works

The harness now waits for offset_committed before stopping recovered Writer. The
repeated experiment records same-offset redelivery, output acknowledgment and
commit of offset + 1. Compose explicitly sets KAFKA_LOG_DIRS to its mounted path;
a real record survived broker-container replacement. Failed first-run output is
retained in RUN_LOG.txt, and corrected measurements are stored in raw/part3/.

After explicit user authorization, the AI reused existing private configuration outside the repository with mode 0600, started the existing database and HW8 API, verified all three account roles and HTTP/Kafka CREATE/GET, and ran all 68 focused tests with zero skipped. Database row values/counts remained unchanged. Actual interactive PTY captures are distinguished from the earlier browser-rendered source/log views. Collaborator membership still requires user GitHub reauthentication and is not labeled verified.
