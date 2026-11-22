package core

import (
	"crypto/rand"
	"fmt"
	"strings"
	"time"
	"unicode"
)

// Invalid constructs a local argument-validation error.
func Invalid(field, message string) *ValidationError {
	return &ValidationError{Field: field, Message: message}
}

// ValidateDuration requires a positive duration.
func ValidateDuration(value time.Duration, field string) error {
	if value <= 0 {
		return Invalid(field, "must be positive")
	}
	return nil
}

func validateRetries(value int) error {
	if value < 0 {
		return Invalid("maxRetries", "must be non-negative")
	}
	return nil
}

// ValidateID catches empty resource IDs before HTTP is sent.
func ValidateID(value, field string) error {
	if strings.TrimSpace(value) == "" {
		return Invalid(field, "must not be empty")
	}
	return nil
}

func validateKey(value string) error {
	if value == "" || len(value) > 200 {
		return Invalid("idempotencyKey", "must be 1-200 bytes")
	}
	for _, char := range value {
		if unicode.IsSpace(char) || unicode.IsControl(char) {
			return Invalid("idempotencyKey", "must not contain whitespace or control characters")
		}
	}
	return nil
}

func randomKey() (string, error) {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return "", fmt.Errorf("traceport: generate idempotency key: %w", err)
	}
	bytes[6] = (bytes[6] & 0x0f) | 0x40
	bytes[8] = (bytes[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", bytes[0:4], bytes[4:6], bytes[6:8], bytes[8:10], bytes[10:16]), nil
}
