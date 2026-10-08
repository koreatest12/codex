# BIFF Planner (Java 21 + Maven)

This small command-line module proves that the repository image contains a working JDK, `javac`, and Maven toolchain while also providing a machine-runnable copy of the BIFF itinerary.

## Requirements

- Java 21+
- Maven 3.8.7+

## Build

```bash
mvn -B -ntp -f java-biff-planner/pom.xml clean package
```

## Run

```bash
java -jar java-biff-planner/target/biff-planner-1.0.0.jar all
java -jar java-biff-planner/target/biff-planner-1.0.0.jar day1
java -jar java-biff-planner/target/biff-planner-1.0.0.jar day2
java -jar java-biff-planner/target/biff-planner-1.0.0.jar food
java -jar java-biff-planner/target/biff-planner-1.0.0.jar toolchain
```

## Container verification

The root Docker image installs OpenJDK 21 JDK (including `javac`) and Maven, compiles this project at image-build time, and keeps the built JAR under:

```text
/opt/java-biff-planner/target/biff-planner-1.0.0.jar
```


## PII masking helper

Mask a sensitive value without placing it in the command-line argument list:

```bash
printf '%s\n' 'SYNTHETIC-BOOKING-1234' | \
  java -jar java-biff-planner/target/biff-planner-1.0.0.jar mask-stdin reservation
```

Do not put real reservation numbers or contact details in source files, command-line arguments, Git history, or logs.
