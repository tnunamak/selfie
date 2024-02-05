# Suppress specific warnings
# TODO: Not sure why these aren't quite working
import logging
import warnings
from llama_index.llms import litellm

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)

litellm.drop_params = True
