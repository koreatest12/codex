#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POM="${ROOT_DIR}/java-biff-planner/pom.xml"
JAR="${ROOT_DIR}/java-biff-planner/target/biff-planner-1.0.0.jar"

echo "==> Java runtime"
java -version

echo "==> Java compiler"
javac -version

echo "==> Maven"
mvn -version

echo "==> Compile/package BIFF planner"
mvn -B -ntp -f "${POM}" clean package

echo "==> Execute planner smoke test"
java -jar "${JAR}" toolchain
java -jar "${JAR}" summary >/dev/null

echo "Java/Javac/Maven/BIFF planner verification: OK"
