FROM golang:1.26-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go build -o control-plane ./cmd/server

FROM alpine:latest

RUN apk --no-cache add ca-certificates docker-cli curl

WORKDIR /root/

COPY --from=builder /app/control-plane .
COPY --from=builder /app/migrations ./migrations

# Download migrate binary
RUN curl -L https://github.com/golang-migrate/migrate/releases/download/v4.16.2/migrate.linux-amd64.tar.gz | tar xvz && \
    mv migrate /usr/local/bin/migrate

EXPOSE 8080

CMD ["./control-plane"]
