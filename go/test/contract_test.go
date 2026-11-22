package test

import (
	"encoding/json"
	"os"
	"reflect"
	"sort"
	"strings"
	"testing"

	"github.com/traceport-ai/sdks/go/workflows"
)

func TestPublicTypesMatchContract(t *testing.T) {
	data, err := os.ReadFile("../../contract/openapi.json")
	if err != nil {
		t.Fatal(err)
	}
	var contract struct {
		Components struct {
			Schemas map[string]struct {
				Properties map[string]struct {
					Enum []string `json:"enum"`
				} `json:"properties"`
			} `json:"schemas"`
		} `json:"components"`
	}
	if err := json.Unmarshal(data, &contract); err != nil {
		t.Fatal(err)
	}
	for _, item := range []struct {
		name  string
		value any
	}{{"WorkflowRun", workflows.Run{}}, {"WorkflowRunBilling", workflows.RunBilling{}}} {
		t.Run(item.name, func(t *testing.T) {
			var fields, properties []string
			typeOf := reflect.TypeOf(item.value)
			for i := 0; i < typeOf.NumField(); i++ {
				tag := strings.Split(typeOf.Field(i).Tag.Get("json"), ",")[0]
				if tag != "-" && tag != "" {
					fields = append(fields, tag)
				}
			}
			for key := range contract.Components.Schemas[item.name].Properties {
				properties = append(properties, key)
			}
			sort.Strings(fields)
			sort.Strings(properties)
			if !reflect.DeepEqual(fields, properties) {
				t.Errorf("Go fields %v != contract %v", fields, properties)
			}
		})
	}
	for _, item := range []struct {
		field  string
		values []string
	}{
		{"status", []string{string(workflows.RunQueued), string(workflows.RunRunning), string(workflows.RunSucceeded), string(workflows.RunFailed), string(workflows.RunInterrupted)}},
		{"mode", []string{string(workflows.ModeProduction), string(workflows.ModeDraftTest)}},
	} {
		expected := contract.Components.Schemas["WorkflowRun"].Properties[item.field].Enum
		sort.Strings(expected)
		sort.Strings(item.values)
		if !reflect.DeepEqual(expected, item.values) {
			t.Errorf("enum %s: %v != %v", item.field, item.values, expected)
		}
	}
	methods := []string{string(workflows.BillingIncluded), string(workflows.BillingWallet), string(workflows.BillingInvoice)}
	expectedMethods := contract.Components.Schemas["WorkflowRunBilling"].Properties["method"].Enum
	sort.Strings(methods)
	sort.Strings(expectedMethods)
	if !reflect.DeepEqual(methods, expectedMethods) {
		t.Errorf("billing method enum: %v != %v", methods, expectedMethods)
	}
}
