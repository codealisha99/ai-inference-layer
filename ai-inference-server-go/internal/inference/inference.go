package inference

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

var idCounter uint64

func nowMs() int64 { return time.Now().UnixMilli() }

func newID() string {
	n := atomic.AddUint64(&idCounter, 1)
	return fmt.Sprintf("%x%x", nowMs(), n)
}

type ModelType string

const (
	TextGeneration     ModelType = "text-generation"
	TextClassification ModelType = "text-classification"
	Embedding          ModelType = "embedding"
)

var ValidTypes = map[ModelType]bool{
	TextGeneration: true, TextClassification: true, Embedding: true,
}

type Model struct {
	ID        string                 `json:"id"`
	Name      string                 `json:"name"`
	Type      ModelType              `json:"type"`
	Config    map[string]interface{} `json:"config"`
	CreatedAt int64                  `json:"createdAt"`
}

type InferenceStatus string

const (
	StatusCompleted InferenceStatus = "completed"
)

type Inference struct {
	ID          string                 `json:"id"`
	ModelID     string                 `json:"modelId"`
	Input       string                 `json:"input"`
	Status      InferenceStatus        `json:"status"`
	Output      map[string]interface{} `json:"output"`
	CreatedAt   int64                  `json:"createdAt"`
	CompletedAt int64                  `json:"completedAt"`
}

func simulate(t ModelType, input string) map[string]interface{} {
	switch t {
	case TextGeneration:
		return map[string]interface{}{"text": fmt.Sprintf("Generated response for: %s", input)}
	case TextClassification:
		return map[string]interface{}{"label": "positive", "score": 0.95}
	case Embedding:
		return map[string]interface{}{"embedding": []float64{0.1, 0.2, 0.3, 0.4, 0.5}}
	}
	return map[string]interface{}{}
}

type Store struct {
	mu         sync.RWMutex
	models     map[string]*Model
	inferences map[string]map[string]*Inference
}

func NewStore() *Store {
	return &Store{
		models:     make(map[string]*Model),
		inferences: make(map[string]map[string]*Inference),
	}
}

func (s *Store) Create(name string, t ModelType, config map[string]interface{}) (*Model, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, m := range s.models {
		if m.Name == name {
			return nil, false
		}
	}
	if config == nil {
		config = make(map[string]interface{})
	}
	id := newID()
	m := &Model{ID: id, Name: name, Type: t, Config: config, CreatedAt: nowMs()}
	s.models[id] = m
	s.inferences[id] = make(map[string]*Inference)
	return m, true
}

func (s *Store) Get(id string) (*Model, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	m, ok := s.models[id]
	return m, ok
}

func (s *Store) List() []Model {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Model, 0, len(s.models))
	for _, m := range s.models {
		out = append(out, *m)
	}
	return out
}

func (s *Store) Delete(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.models[id]; !ok {
		return false
	}
	delete(s.models, id)
	delete(s.inferences, id)
	return true
}

func (s *Store) RunInference(modelID, input string) (*Inference, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	m, ok := s.models[modelID]
	if !ok {
		return nil, false
	}
	now := nowMs()
	inf := &Inference{
		ID:          newID(),
		ModelID:     modelID,
		Input:       input,
		Status:      StatusCompleted,
		Output:      simulate(m.Type, input),
		CreatedAt:   now,
		CompletedAt: now,
	}
	s.inferences[modelID][inf.ID] = inf
	return inf, true
}

func (s *Store) ListInferences(modelID string) ([]Inference, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	bucket, ok := s.inferences[modelID]
	if !ok {
		return nil, false
	}
	out := make([]Inference, 0, len(bucket))
	for _, inf := range bucket {
		out = append(out, *inf)
	}
	return out, true
}

func (s *Store) GetInference(modelID, inferenceID string) (*Inference, bool, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	bucket, ok := s.inferences[modelID]
	if !ok {
		return nil, false, false
	}
	inf, ok2 := bucket[inferenceID]
	return inf, true, ok2
}
