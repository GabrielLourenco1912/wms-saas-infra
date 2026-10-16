# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /var/www/html

COPY pom.xml .
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp dependency:go-offline

COPY src/main ./src/main
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp clean package -Dmaven.test.skip=true

FROM eclipse-temurin:21-jre AS runner

LABEL org.opencontainers.image.title="WMS SaaS Backend" \
      org.opencontainers.image.source="https://github.com/GabrielLourenco1912/wms-saas-backend"

WORKDIR /var/www/html

RUN groupadd --gid 1001 springuser \
    && useradd --uid 1001 --gid springuser --create-home springuser \
    && chown springuser:springuser /var/www/html

COPY --from=builder --chown=1001:1001 /var/www/html/target/*.jar app.jar

USER 1001:1001
EXPOSE 8080

CMD ["java", "-jar", "app.jar"]
