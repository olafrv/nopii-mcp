import warnings

# Harmless deprecation noise from libraries we don't control:
# transformers' DeBERTa code (used by GLiNER) calls torch.jit.script on import,
# and GLiNER passes resume_download to huggingface_hub when loading the model.
warnings.filterwarnings("ignore", message=r"`torch\.jit\.script` is deprecated", category=FutureWarning)
warnings.filterwarnings("ignore", message=r"The `resume_download` argument is deprecated", category=UserWarning)
