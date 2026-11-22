package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestParseSamples(t *testing.T) {
	body := []byte(`{"status":"success","data":{"result":[{"metric":{"instance":"node-a:9100"},"value":[1700000000,"0.25"]}]}}`)
	nodes, err := parseSamples(body)
	if err != nil {
		t.Fatal(err)
	}
	if len(nodes) != 1 || nodes[0].Instance != "node-a:9100" || nodes[0].Ratio != 0.25 {
		t.Fatalf("unexpected samples: %#v", nodes)
	}
}

func TestParseSamplesRejectsInvalidRatio(t *testing.T) {
	body := []byte(`{"status":"success","data":{"result":[{"metric":{"instance":"node-a"},"value":[1,"1.5"]}]}}`)
	if _, err := parseSamples(body); err == nil {
		t.Fatal("expected invalid ratio error")
	}
}

func TestParseSamplesRejectsPrometheusError(t *testing.T) {
	if _, err := parseSamples([]byte(`{"status":"error"}`)); err == nil {
		t.Fatal("expected status error")
	}
}

func TestQueryPrometheus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/query" || !strings.Contains(r.URL.Query().Get("query"), "node_memory_MemAvailable_bytes") {
			t.Errorf("unexpected request: %s", r.URL.String())
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"success","data":{"result":[{"metric":{"instance":"node-a"},"value":[1,"0.08"]}]}}`))
	}))
	defer server.Close()
	nodes, err := queryPrometheus(server.URL, 0.10)
	if err != nil {
		t.Fatal(err)
	}
	if len(nodes) != 1 || nodes[0].Ratio != 0.08 {
		t.Fatalf("unexpected result: %#v", nodes)
	}
}

func TestQueryRejectsInvalidThreshold(t *testing.T) {
	if _, err := queryPrometheus("http://localhost:9090", 1); err == nil {
		t.Fatal("expected threshold validation error")
	}
}
