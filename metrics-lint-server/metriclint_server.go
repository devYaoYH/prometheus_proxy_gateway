package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"

	"github.com/prometheus/client_golang/prometheus/testutil/promlint"
)

type LintResponse struct {
	Status    string           `json:"status"`
	Message   string           `json:"message,omitempty"`
	Problems  []ProblemDetails `json:"problems,omitempty"`
	ErrorText string           `json:"error,omitempty"`
}

type ProblemDetails struct {
	Metric string `json:"metric"`
	Text   string `json:"text"`
}

func main() {
	// Set up the server
	http.HandleFunc("/lint", handleLint)
	
	port := 8080
	fmt.Printf("Starting metrics linter server on port %d...\n", port)
	if err := http.ListenAndServe(fmt.Sprintf(":%d", port), nil); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

func handleLint(w http.ResponseWriter, r *http.Request) {
	// Only accept PUT method
	if r.Method != http.MethodPut {
		http.Error(w, "Method not allowed. Use PUT.", http.StatusMethodNotAllowed)
		return
	}

	// Read the body
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read request body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	metricsText := string(body)
	
	// Set response headers
	w.Header().Set("Content-Type", "application/json")
	
	// Create response object
	response := LintResponse{}
	
	// Check for empty input
	if strings.TrimSpace(metricsText) == "" {
		response.Status = "error"
		response.Message = "No input provided. Please send metrics in the request body."
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(response)
		return
	}

	// Run the linter
	metrics := strings.NewReader(metricsText + "\n")
	l := promlint.New(metrics)
	problems, err := l.Lint()
	
	if err != nil {
		// Handle parsing error
		response.Status = "error"
		response.ErrorText = err.Error()
		response.Message = "Failed to parse metrics"
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(response)
		return
	}

	if len(problems) == 0 {
		// No problems found
		response.Status = "success"
		response.Message = "Input has been parsed successfully. No issues found."
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(response)
		return
	}

	// Problems found
	response.Status = "warning"
	response.Message = "The input can be parsed but there are linting issues"
	response.Problems = make([]ProblemDetails, 0, len(problems))
	
	for _, p := range problems {
		response.Problems = append(response.Problems, ProblemDetails{
			Metric: p.Metric,
			Text:   p.Text,
		})
	}
	
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}