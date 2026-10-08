package handler_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"ai-inference-server-go/internal/handler"
	"ai-inference-server-go/internal/inference"
)

func newServer() http.Handler { return handler.Router(inference.NewStore()) }

func do(h http.Handler, method, path string, body interface{}) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	if body != nil {
		_ = json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(method, path, &buf)
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

func jsonBody(rr *httptest.ResponseRecorder) map[string]interface{} {
	var m map[string]interface{}
	_ = json.NewDecoder(rr.Body).Decode(&m)
	return m
}

func data(rr *httptest.ResponseRecorder) interface{}               { return jsonBody(rr)["data"] }
func dataMap(rr *httptest.ResponseRecorder) map[string]interface{} { d, _ := data(rr).(map[string]interface{}); return d }
func dataArr(rr *httptest.ResponseRecorder) []interface{}          { d, _ := data(rr).([]interface{}); return d }

func createModel(h http.Handler, name, typ string) *httptest.ResponseRecorder {
	return do(h, "POST", "/models", map[string]interface{}{"name": name, "type": typ})
}

func TestHealth(t *testing.T) {
	rr := do(newServer(), "GET", "/health", nil)
	if rr.Code != 200 {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
}

func TestCreateModel(t *testing.T) {
	rr := createModel(newServer(), "gpt", "text-generation")
	if rr.Code != 201 {
		t.Fatalf("expected 201 got %d: %s", rr.Code, rr.Body)
	}
	d := dataMap(rr)
	if d["name"] != "gpt" {
		t.Errorf("wrong name: %v", d["name"])
	}
}

func TestCreateModelMissingName(t *testing.T) {
	rr := do(newServer(), "POST", "/models", map[string]interface{}{"type": "embedding"})
	if rr.Code != 400 {
		t.Fatalf("expected 400 got %d", rr.Code)
	}
}

func TestCreateModelInvalidType(t *testing.T) {
	rr := do(newServer(), "POST", "/models", map[string]interface{}{"name": "x", "type": "badtype"})
	if rr.Code != 400 {
		t.Fatalf("expected 400 got %d", rr.Code)
	}
}

func TestCreateModelMissingType(t *testing.T) {
	rr := do(newServer(), "POST", "/models", map[string]interface{}{"name": "x"})
	if rr.Code != 400 {
		t.Fatalf("expected 400 got %d", rr.Code)
	}
}

func TestCreateModelDuplicate(t *testing.T) {
	h := newServer()
	createModel(h, "gpt", "text-generation")
	rr := createModel(h, "gpt", "text-generation")
	if rr.Code != 409 {
		t.Fatalf("expected 409 got %d", rr.Code)
	}
}

func TestCreateModelAllTypes(t *testing.T) {
	for _, typ := range []string{"text-generation", "text-classification", "embedding"} {
		rr := createModel(newServer(), "model-"+typ, typ)
		if rr.Code != 201 {
			t.Errorf("type %s: expected 201 got %d", typ, rr.Code)
		}
	}
}

func TestListModels(t *testing.T) {
	h := newServer()
	createModel(h, "m1", "embedding")
	createModel(h, "m2", "text-classification")
	rr := do(h, "GET", "/models", nil)
	if rr.Code != 200 {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
	if len(dataArr(rr)) != 2 {
		t.Errorf("expected 2 models got %d", len(dataArr(rr)))
	}
}

func TestGetModel(t *testing.T) {
	h := newServer()
	d := dataMap(createModel(h, "gpt", "text-generation"))
	rr := do(h, "GET", "/models/"+d["id"].(string), nil)
	if rr.Code != 200 {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
}

func TestGetModelNotFound(t *testing.T) {
	rr := do(newServer(), "GET", "/models/nope", nil)
	if rr.Code != 404 {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}

func TestDeleteModel(t *testing.T) {
	h := newServer()
	d := dataMap(createModel(h, "gpt", "text-generation"))
	id := d["id"].(string)
	rr := do(h, "DELETE", "/models/"+id, nil)
	if rr.Code != 200 {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
	check := do(h, "GET", "/models/"+id, nil)
	if check.Code != 404 {
		t.Fatalf("expected 404 after delete got %d", check.Code)
	}
}

func TestDeleteModelNotFound(t *testing.T) {
	rr := do(newServer(), "DELETE", "/models/nope", nil)
	if rr.Code != 404 {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}

func TestRunInference(t *testing.T) {
	h := newServer()
	id := dataMap(createModel(h, "gpt", "text-generation"))["id"].(string)
	rr := do(h, "POST", "/models/"+id+"/infer", map[string]interface{}{"input": "hello"})
	if rr.Code != 201 {
		t.Fatalf("expected 201 got %d: %s", rr.Code, rr.Body)
	}
	d := dataMap(rr)
	if d["status"] != "completed" {
		t.Errorf("expected completed got %v", d["status"])
	}
	if d["output"] == nil {
		t.Error("output should not be nil")
	}
}

func TestRunInferenceMissingInput(t *testing.T) {
	h := newServer()
	id := dataMap(createModel(h, "gpt", "text-generation"))["id"].(string)
	rr := do(h, "POST", "/models/"+id+"/infer", map[string]interface{}{})
	if rr.Code != 400 {
		t.Fatalf("expected 400 got %d", rr.Code)
	}
}

func TestRunInferenceNotFound(t *testing.T) {
	rr := do(newServer(), "POST", "/models/nope/infer", map[string]interface{}{"input": "hi"})
	if rr.Code != 404 {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}

func TestTextGenerationOutput(t *testing.T) {
	h := newServer()
	id := dataMap(createModel(h, "gen", "text-generation"))["id"].(string)
	rr := do(h, "POST", "/models/"+id+"/infer", map[string]interface{}{"input": "hi"})
	out := dataMap(rr)["output"].(map[string]interface{})
	if out["text"] == nil {
		t.Error("text-generation output should have 'text'")
	}
}

func TestTextClassificationOutput(t *testing.T) {
	h := newServer()
	id := dataMap(createModel(h, "cls", "text-classification"))["id"].(string)
	rr := do(h, "POST", "/models/"+id+"/infer", map[string]interface{}{"input": "hi"})
	out := dataMap(rr)["output"].(map[string]interface{})
	if out["label"] == nil {
		t.Error("text-classification output should have 'label'")
	}
}

func TestEmbeddingOutput(t *testing.T) {
	h := newServer()
	id := dataMap(createModel(h, "emb", "embedding"))["id"].(string)
	rr := do(h, "POST", "/models/"+id+"/infer", map[string]interface{}{"input": "hi"})
	out := dataMap(rr)["output"].(map[string]interface{})
	if out["embedding"] == nil {
		t.Error("embedding output should have 'embedding'")
	}
}

func TestListInferences(t *testing.T) {
	h := newServer()
	mid := dataMap(createModel(h, "gpt", "text-generation"))["id"].(string)
	do(h, "POST", "/models/"+mid+"/infer", map[string]interface{}{"input": "a"})
	do(h, "POST", "/models/"+mid+"/infer", map[string]interface{}{"input": "b"})
	rr := do(h, "GET", "/models/"+mid+"/inferences", nil)
	if rr.Code != 200 {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
	if len(dataArr(rr)) != 2 {
		t.Errorf("expected 2 inferences got %d", len(dataArr(rr)))
	}
}

func TestListInferencesNotFound(t *testing.T) {
	rr := do(newServer(), "GET", "/models/nope/inferences", nil)
	if rr.Code != 404 {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}

func TestGetInference(t *testing.T) {
	h := newServer()
	mid := dataMap(createModel(h, "gpt", "text-generation"))["id"].(string)
	inf := dataMap(do(h, "POST", "/models/"+mid+"/infer", map[string]interface{}{"input": "x"}))
	infID := inf["id"].(string)
	rr := do(h, "GET", "/models/"+mid+"/inferences/"+infID, nil)
	if rr.Code != 200 {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
}

func TestGetInferenceNotFound(t *testing.T) {
	h := newServer()
	mid := dataMap(createModel(h, "gpt", "text-generation"))["id"].(string)
	rr := do(h, "GET", "/models/"+mid+"/inferences/nope", nil)
	if rr.Code != 404 {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}

func TestGetInferenceModelNotFound(t *testing.T) {
	rr := do(newServer(), "GET", "/models/nope/inferences/x", nil)
	if rr.Code != 404 {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}
