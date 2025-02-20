from zeeguu.core.tokenization.token import Token
from zeeguu.core.tokenization.zeeguu_tokenizer import ZeeguuTokenizer, TokenizerModel
from zeeguu.core.model.language import Language
import re
from zeeguu.config import ZEEGUU_RESOURCES_FOLDER

import stanza
import os

STANZA_PARAGRAPH_DELIMITER = re.compile(r"((\s?)+\\n+)")
APOSTROPHE_BEFORE_WORD = re.compile(r" (')([\w]+)")
# This is used to capture the l' from l'autheur
PARTICLE_WITH_APOSTROPHE = re.compile(r"(\w+('|’))")


URL_PLACEHOLDER = "#URL#"
EMAIL_PLACEHOLDER = "#EMAIL#"


STANZA_RESOURCE_DIR = os.path.join(ZEEGUU_RESOURCES_FOLDER, "stanza_resources")


class StanzaTokenizer(ZeeguuTokenizer):
    STANZA_MODELS = set(
        [TokenizerModel.STANZA_TOKEN_ONLY, TokenizerModel.STANZA_TOKEN_POS]
    )
    # We cache the models to avoid having to re-initialize pipelines everytime.
    # Once the model is loaded it's kept in memory for later use.
    CACHED_NLP_PIPELINES = {}

    def _get_processor(model: TokenizerModel):
        if model == TokenizerModel.STANZA_TOKEN_ONLY:
            return "tokenize"
        elif model == TokenizerModel.STANZA_TOKEN_POS:
            return "tokenize,pos"
        return ""

    def __init__(self, language: Language, model: TokenizerModel):
        super().__init__(language, model)
        key = (self.language.code, self.model_type)
        if self.model_type in StanzaTokenizer.STANZA_MODELS:
            # Store used models.
            if key not in StanzaTokenizer.CACHED_NLP_PIPELINES:
                pipeline = stanza.Pipeline(
                    lang=self.language.code,
                    processors=StanzaTokenizer._get_processor(model),
                    download_method=None,
                    model_dir=STANZA_RESOURCE_DIR,
                )
                StanzaTokenizer.CACHED_NLP_PIPELINES[key] = pipeline
        self.nlp_pipeline = StanzaTokenizer.CACHED_NLP_PIPELINES[key]

    def is_language_supported(self, language: Language):
        #   This is based on the models installed, if we expand the languages we support
        # we then have to install them too.
        return language.name.lower() in Language.CODES_OF_LANGUAGES_THAT_CAN_BE_LEARNED

    def _get_token(
        self,
        t,
        par_i,
        sent_i,
        w_i,
        has_space,
        as_serializable_dictionary,
        pos=None,
    ):
        token = Token(t, par_i, sent_i, w_i, has_space, pos)
        if as_serializable_dictionary:
            return token.as_serializable_dictionary()
        return token

    def tokenize_text(
        self,
        text: str,
        as_serializable_dictionary: bool = True,
        flatten: bool = True,
        start_token_i: int = 0,
        start_sentence_i: int = 0,
        start_paragraph_i: int = 0,
    ):
        # Backwards compatability (to texts without coordinates.)
        if start_token_i is None:
            start_token_i = 0
        if start_sentence_i is None:
            start_sentence_i = 0
        if start_paragraph_i is None:
            start_paragraph_i = 0
        paragraphs = []
        doc = self.nlp_pipeline(text)
        current_paragraph = []
        s_i = 0
        for sentence in doc.sentences:
            sent_list = []
            is_new_paragraph = False
            accumulator = ""
            t_i = 0
            for i, token in enumerate(sentence.tokens):
                # Stanza's to_dict returns a list of token dictionaries.
                # This is because some tokens can be "composed."
                t_details = token.to_dict()[0]
                text = t_details["text"]
                particle_with_apostrophe = PARTICLE_WITH_APOSTROPHE.match(
                    t_details["text"]
                )
                has_space = not ("SpaceAfter=No" in t_details.get("misc", ""))
                if (
                    particle_with_apostrophe
                    and particle_with_apostrophe.group(0) == text
                    and i + 1 < len(sentence.tokens)
                    and sentence.tokens[i + 1].text
                    not in Token.PUNCTUATION  # avoid situations like call'? where it's followed by a punctuation
                    and not has_space
                ):
                    # Do not accumulate in case it's the only token in the sentence.
                    # Handles the case where in French and Italian the tokens are seperated
                    # e.g. l'un, we want l'un as a token rather than l' and un
                    #      avoid also cases where it would find a punctuation (typen'?)
                    accumulator += text
                    continue

                if accumulator != "":
                    # Combine the acumulated token with the current token.
                    text = accumulator + text
                    accumulator = ""

                sent_list.append(
                    self._get_token(
                        text,
                        len(paragraphs) + start_paragraph_i,
                        s_i + start_sentence_i,
                        t_i + start_token_i,
                        has_space,
                        as_serializable_dictionary,
                        pos=t_details.get("upos", None),
                    )
                )
                t_i += 1
                if STANZA_PARAGRAPH_DELIMITER.search(t_details.get("misc", "")):
                    is_new_paragraph = True
            current_paragraph.append(sent_list)
            s_i += 1
            if is_new_paragraph:
                paragraphs.append(current_paragraph)
                current_paragraph = []
                s_i = 0
        paragraphs.append(current_paragraph)

        if flatten:
            paragraphs = self._flatten_paragraph_list(paragraphs)
        return paragraphs

    def get_sentences(self, text: str):
        doc = self.nlp_pipeline(text)
        return [
            " ".join([token.text for token in sent.tokens]) for sent in doc.sentences
        ]
