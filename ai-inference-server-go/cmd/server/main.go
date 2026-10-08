package main

import (
	"fmt"
	"net/http"
	"os"

	"ai-inference-server-go/internal/handler"
	"ai-inference-server-go/internal/inference"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "3000"
	}
	s := inference.NewStore()
	router := handler.Router(s)
	fmt.Fprintf(os.Stderr, "ai-inference-server listening on :%s\n", port)
	if err := http.ListenAndServe(":"+port, router); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
