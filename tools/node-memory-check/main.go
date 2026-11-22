package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"time"
)

type sample struct {
	Metric map[string]string `json:"metric"`
	Value  []json.RawMessage `json:"value"`
}

type queryResponse struct {
	Status string `json:"status"`
	Data struct {
		Result []sample `json:"result"`
	} `json:"data"`
}

type nodeMemory struct {
	Instance string
	Ratio    float64
}

func parseSamples(body []byte) ([]nodeMemory, error) {
	var response queryResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("decode Prometheus response: %w", err)
	}
	if response.Status != "success" {
		return nil, errors.New("Prometheus query did not return success")
	}
	results := make([]nodeMemory, 0, len(response.Data.Result))
	for _, item := range response.Data.Result {
		if len(item.Value) != 2 {
			return nil, errors.New("Prometheus sample must contain timestamp and value")
		}
		var raw string
		if err := json.Unmarshal(item.Value[1], &raw); err != nil {
			return nil, fmt.Errorf("decode sample value: %w", err)
		}
		ratio, err := strconv.ParseFloat(raw, 64)
		if err != nil || ratio < 0 || ratio > 1 {
			return nil, fmt.Errorf("invalid available-memory ratio %q", raw)
		}
		instance := item.Metric["instance"]
		if instance == "" {
			instance = "unknown"
		}
		results = append(results, nodeMemory{Instance: instance, Ratio: ratio})
	}
	return results, nil
}

func queryPrometheus(baseURL string, threshold float64) ([]nodeMemory, error) {
	if threshold <= 0 || threshold >= 1 {
		return nil, errors.New("threshold must be greater than 0 and less than 1")
	}
	parsed, err := url.Parse(baseURL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return nil, errors.New("PROMETHEUS_URL must be an absolute http(s) URL")
	}
	parsed.Path = "/api/v1/query"
	params := parsed.Query()
	params.Set("query", `sum by (instance) (node_memory_MemAvailable_bytes) / sum by (instance) (node_memory_MemTotal_bytes)`)
	parsed.RawQuery = params.Encode()

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(parsed.String())
	if err != nil {
		return nil, fmt.Errorf("query Prometheus: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Prometheus returned HTTP %s", resp.Status)
	}
	var body json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, fmt.Errorf("read Prometheus response: %w", err)
	}
	nodes, err := parseSamples(body)
	if err != nil {
		return nil, err
	}
	for _, node := range nodes {
		state := "OK"
		if node.Ratio < threshold {
			state = "WARNING"
		}
		fmt.Printf("%-24s available=%5.1f%% threshold=%5.1f%% %s\n", node.Instance, node.Ratio*100, threshold*100, state)
	}
	if len(nodes) == 0 {
		fmt.Println("No node memory samples returned; check Prometheus scrape configuration.")
	}
	return nodes, nil
}

func main() {
	threshold := flag.Float64("threshold", 0.10, "warning threshold for available memory (0–1)")
	flag.Parse()
	endpoint := os.Getenv("PROMETHEUS_URL")
	if endpoint == "" {
		fmt.Fprintln(os.Stderr, "PROMETHEUS_URL is required (for example http://localhost:9090)")
		os.Exit(2)
	}
	if _, err := queryPrometheus(endpoint, *threshold); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
