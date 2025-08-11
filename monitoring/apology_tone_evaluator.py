import os
from typing import Dict, List, Union
from typing_extensions import overload, override

from azure.ai.evaluation._evaluators._common import PromptyEvaluatorBase
from azure.ai.evaluation._model_configurations import Conversation


class ApologyToneEvaluator(PromptyEvaluatorBase[Union[str, float]]):
    """
    Evaluates the level of apologetic language in AI responses on a 1-5 scale.

    This evaluator measures how much apologetic language is present in the response,
    providing a neutral quantification without judging appropriateness.
    
    :param model_config: Configuration for the Azure OpenAI model.
    :type model_config: Union[~azure.ai.evaluation.AzureOpenAIModelConfiguration,
        ~azure.ai.evaluation.OpenAIModelConfiguration]
    :param threshold: The threshold for the apology tone evaluator. Default is 3.
    :type threshold: float
    """

    _PROMPTY_FILE = "apology_tone.prompty"
    _RESULT_KEY = "apology_tone"

    id = "azureai://built-in/evaluators/apology_tone"

    @override
    def __init__(self, model_config, *, threshold=3.0):
        current_dir = os.path.dirname(__file__)
        prompty_path = os.path.join(current_dir, self._PROMPTY_FILE)
        self._threshold = threshold
        self._higher_is_better = True 
        super().__init__(
            model_config=model_config,
            prompty_file=prompty_path,
            result_key=self._RESULT_KEY,
            threshold=threshold,
            _higher_is_better=self._higher_is_better,
        )

    @overload
    def __call__(
        self,
        *,
        query: str,
        response: str,
    ) -> Dict[str, Union[str, float]]:
        """Evaluate apology tone for given input of query and response

        :keyword query: The query to be evaluated.
        :paramtype query: str
        :keyword response: The response to be evaluated.
        :paramtype response: str
        :return: The apology tone score.
        :rtype: Dict[str, Union[str, float]]
        """

    @overload
    def __call__(
        self,
        *,
        conversation: Conversation,
    ) -> Dict[str, Union[float, Dict[str, List[Union[str, float]]]]]:
        """Evaluate apology tone for a conversation

        :keyword conversation: The conversation to evaluate.
        :paramtype conversation: Optional[~azure.ai.evaluation.Conversation]
        :return: The apology tone score.
        :rtype: Dict[str, Union[float, Dict[str, List[Union[str, float]]]]]
        """

    @override
    def __call__(
        self,
        *args,
        **kwargs,
    ):
        """Evaluate apology tone. Accepts either a query and response for a single evaluation,
        or a conversation for a multi-turn evaluation.

        :return: The apology tone score (1-5 scale).
        :rtype: Union[Dict[str, Union[str, float]], Dict[str, Union[float, Dict[str, List[Union[str, float]]]]]]
        """
        return super().__call__(*args, **kwargs)
