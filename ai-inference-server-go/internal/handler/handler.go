package handler

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"ai-inference-server-go/internal/inference"
)

type Handler struct{ store *inference.Store }

func New(s *inference.Store) *Handler { return &Handler{store: s} }

func respond(w http.ResponseWriter, status int, data interface{}, errMsg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	success := errMsg == ""
	var errVal interface{}
	if errMsg != "" {
		errVal = errMsg
	}
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"success": success, "data": data, "error": errVal,
	})
}

func ok(w http.ResponseWriter, data interface{})       { respond(w, http.StatusOK, data, "") }
func created(w http.ResponseWriter, data interface{})  { respond(w, http.StatusCreated, data, "") }
func badReq(w http.ResponseWriter, msg string)         { respond(w, http.StatusBadRequest, nil, msg) }
func notFound(w http.ResponseWriter, msg string)       { respond(w, http.StatusNotFound, nil, msg) }
func conflict(w http.ResponseWriter, msg string)       { respond(w, http.StatusConflict, nil, msg) }

func parseBody(w http.ResponseWriter, r *http.Request, dst interface{}) bool {
	if err := json.NewDecoder(r.Body).Decode(dst); err != nil {
		badReq(w, "invalid JSON")
		return false
	}
	return true
}

func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
	ok(w, map[string]string{"status": "ok"})
}

type createBody struct {
	Name   string                 `json:"name"`
	Type   string                 `json:"type"`
	Config map[string]interface{} `json:"config"`
}

func (h *Handler) CreateModel(w http.ResponseWriter, r *http.Request) {
	var body createBody
	if !parseBody(w, r, &body) {
		return
	}
	if body.Name == "" {
		badReq(w, "name is required")
		return
	}
	if !inference.ValidTypes[inference.ModelType(body.Type)] {
		badReq(w, "type must be one of: text-generation, text-classification, embedding")
		return
	}
	m, ok2 := h.store.Create(body.Name, inference.ModelType(body.Type), body.Config)
	if !ok2 {
		conflict(w, "model with that name already exists")
		return
	}
	created(w, m)
}

func (h *Handler) ListModels(w http.ResponseWriter, r *http.Request) {
	ok(w, h.store.List())
}

func (h *Handler) GetModel(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	m, found := h.store.Get(id)
	if !found {
		notFound(w, "model not found")
		return
	}
	ok(w, m)
}

func (h *Handler) DeleteModel(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !h.store.Delete(id) {
		notFound(w, "model not found")
		return
	}
	ok(w, map[string]interface{}{"id": id, "removed": true})
}

type inferBody struct {
	Input string `json:"input"`
}

func (h *Handler) RunInference(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	var body inferBody
	if !parseBody(w, r, &body) {
		return
	}
	if body.Input == "" {
		badReq(w, "input is required")
		return
	}
	inf, found := h.store.RunInference(id, body.Input)
	if !found {
		notFound(w, "model not found")
		return
	}
	created(w, inf)
}

func (h *Handler) ListInferences(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	list, found := h.store.ListInferences(id)
	if !found {
		notFound(w, "model not found")
		return
	}
	ok(w, list)
}

func (h *Handler) GetInference(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	infID := chi.URLParam(r, "inferenceId")
	inf, mFound, iFound := h.store.GetInference(id, infID)
	if !mFound {
		notFound(w, "model not found")
		return
	}
	if !iFound {
		notFound(w, "inference not found")
		return
	}
	ok(w, inf)
}

func Router(s *inference.Store) http.Handler {
	h := New(s)
	r := chi.NewRouter()
	r.Get("/health", h.Health)
	r.Post("/models", h.CreateModel)
	r.Get("/models", h.ListModels)
	r.Get("/models/{id}", h.GetModel)
	r.Delete("/models/{id}", h.DeleteModel)
	r.Post("/models/{id}/infer", h.RunInference)
	r.Get("/models/{id}/inferences", h.ListInferences)
	r.Get("/models/{id}/inferences/{inferenceId}", h.GetInference)
	return r
}
