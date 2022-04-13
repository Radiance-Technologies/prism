# PRISM

Pretraining for Proof Repair with Imposed Syntax Modeling

## Description

PRISM is a framework to enable the augmentation of pretrained language models (LMs) with syntactical\
 and semantic relational knowledge captured via graph neural networks (GNNs) for efficient proof generation\
  and repair with limited data. The LM aids in the generation of well-structured code while reinforcement learning (RL)\
   ensures proof correctness and localization. PRISM will culminate in a prototype IDE extension that uses the developed\
    machine learning (ML) model to propose proofs or proof(-related) repairs for regions of code prompted by the user.

## Getting Started

### Environment Setup
* Navigate to top `prism` directory
* Create Python virtual environment (default version is 3.9.10)
```
source setup_python.sh [Python 3 version (optional)]
```
* Install Coq (default version is 8.10.2, alternative versions not currently supported)
* May need to run `opam init` to sucessfully install Coq
```
source setup_coq.sh
```
* Install additional dependencies in virtual environment
```
pip install -r requirements.txt
```