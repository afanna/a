"""Information Completeness Rules (Dimension: information, 25 pts).



Rule 1.1 - Intent Entity Missing: Verify intent-specific entities appear in OCR.

Rule 1.2 - Text Truncation: OCR detects truncated / low-confidence text.

Rule 1.3 - Information Redundancy: duplicate or near-duplicate text blocks.

Rule 1.4 - Entity Missing: expected structured entities absent.

"""



from __future__ import annotations



from difflib import SequenceMatcher



from card_scorer.analyzers.intent import get_classifier

from card_scorer.models import RuleResult, Severity, ScoringContext

from card_scorer.rules.base import Rule

from card_scorer.rules.registry import register_rule





@register_rule

class KeywordMissingRule(Rule):

    """R1.1: Check if intent-specific entities appear in OCR text.



    Replaces simple keyword matching with intent classification + entity validation.

    See: INTENT_MATCHING.md

    """



    rule_id = "R1.1"

    rule_name = "信息完整性"

    dimension = "information"

    severity = Severity.FATAL

    max_deduction = 10.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        # Get OCR texts

        ocr_texts = [e.text for e in ctx.text_elements if e.text.strip()]



        # Classify intent and match entities

        classifier = get_classifier()

        result = classifier.analyze(ctx.query, ocr_texts)



        # Store in context for reporting

        ctx.intent_result = result.to_dict()



        # Case 1: Perfect - has required entities

        if result.has_required_entities:

            return self._pass({

                "intent": result.intent_name,

                "confidence": result.confidence,

                "matched_keywords": result.matched_keywords,

                "matched_entities": result.matched_entities,

            })



        # Case 2: No entities found at all - severe deduction

        if not result.matched_entities and not result.all_text_has_content:

            return self._fail(

                deduction=self.max_deduction,

                evidence={

                    "intent": result.intent_name,

                    "matched_keywords": result.matched_keywords,

                    "matched_entities": [],

                    "missing_required_entities": result.missing_required_entities,

                },

                explanation=f"未检测到任何{result.intent_name}相关信息",

                suggestion=f"检查卡片是否正确渲染了{result.intent_name}的关键信息",

            )



        # Case 3: Has some content but missing required entities

        if result.missing_required_entities:

            # Deduction based on how many required entities are missing

            num_missing = len(result.missing_required_entities)

            if num_missing >= 2:

                deduction = self.max_deduction

            else:

                deduction = 5.0



            return self._fail(

                deduction=deduction,

                evidence={

                    "intent": result.intent_name,

                    "matched_keywords": result.matched_keywords,

                    "matched_entities": result.matched_entities,

                    "missing_required_entities": result.missing_required_entities,

                },

                explanation=f"缺少{result.intent_name}必需信息: {', '.join(result.missing_required_entities)}",

                suggestion=f"补充卡片中缺失的{result.intent_name}信息",

            )



        # Case 4: General fallback - check content quality, not just existence

        if result.intent_name == "GENERAL":

            # For GENERAL intent, require more than just minimal text

            # Check if OCR found substantial content (>= 3 text elements)

            if len(ocr_texts) >= 3 and result.all_text_has_content:

                return self._pass({

                    "intent": "GENERAL",

                    "confidence": result.confidence,

                    "matched_keywords": result.matched_keywords,

                    "matched_entities": result.matched_entities,

                })

            else:

                # Too little content for GENERAL - likely OCR failed

                return self._fail(

                    deduction=5.0,

                    evidence={

                        "intent": "GENERAL",

                        "text_count": len(ocr_texts),

                        "confidence": result.confidence,

                    },

                    explanation=f"OCR 仅识别到 {len(ocr_texts)} 个文本块，可能存在识别失败",

                    suggestion="检查图片质量、文字对比度、字号大小",

                )



        # Default: Pass (shouldn't reach here)

        return self._pass({

            "intent": result.intent_name,

            "fallback": True,

        })





@register_rule

class TextTruncationRule(Rule):

    """R1.2: Detect truncated text (low confidence or trailing ellipsis)."""



    rule_id = "R1.2"

    rule_name = "文本截断"

    dimension = "information"

    severity = Severity.FATAL

    max_deduction = 8.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        threshold = self.cfg.threshold("information", "truncation_confidence_threshold")

        truncated = []



        for elem in ctx.text_elements:

            is_truncated = False

            reason = ""

            # Low confidence may indicate partial recognition

            if elem.confidence < threshold:

                is_truncated = True

                reason = f"低置信度 {elem.confidence:.2f}"

            # Trailing ellipsis

            if elem.text.rstrip().endswith("...") or elem.text.rstrip().endswith(".."):

                is_truncated = True

                reason = f"文本以省略号结尾: '{elem.text}'"



            if is_truncated:

                truncated.append({"text": elem.text, "confidence": elem.confidence, "reason": reason})



        if not truncated:

            return self._pass()



        deduction = self.cfg.threshold("information", "truncation_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"truncated_items": truncated},

            explanation=f"检测到 {len(truncated)} 处文本截断",

            suggestion="检查文本是否完整渲染，避免溢出容器",

        )





@register_rule

class InformationRedundancyRule(Rule):

    """R1.3: Detect duplicate / near-duplicate text blocks."""



    rule_id = "R1.3"

    rule_name = "信息冗余"

    dimension = "information"

    severity = Severity.MINOR

    max_deduction = 5.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        threshold = self.cfg.threshold("information", "redundancy_similarity_threshold")

        texts = [e.text.strip() for e in ctx.text_elements if e.text.strip()]

        duplicates = []



        for i in range(len(texts)):

            for j in range(i + 1, len(texts)):

                sim = SequenceMatcher(None, texts[i], texts[j]).ratio()

                if sim >= threshold:

                    duplicates.append({

                        "text_a": texts[i],

                        "text_b": texts[j],

                        "similarity": round(sim, 3),

                    })



        if not duplicates:

            return self._pass()



        deduction = self.cfg.threshold("information", "redundancy_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"duplicates": duplicates},

            explanation=f"检测到 {len(duplicates)} 组重复/相似文本",

            suggestion="移除冗余文本，保持信息简洁",

        )





@register_rule

class EntityMissingRule(Rule):

    """R1.4: Structured entity check (e.g. date, temperature, location).



    This is a placeholder that checks if the card has minimal content.

    In production, entity types would be inferred from query context.

    """



    rule_id = "R1.4"

    rule_name = "关键实体缺失"

    dimension = "information"

    severity = Severity.MAJOR

    max_deduction = 7.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        # Basic check: card should have at least some text

        if len(ctx.text_elements) == 0 and len(ctx.component_elements) == 0:

            return self._fail(

                deduction=self.max_deduction,

                evidence={"text_count": 0, "component_count": 0},

                explanation="卡片中未检测到任何文本或视觉元素",

                suggestion="检查卡片是否正确渲染",

            )



        if len(ctx.text_elements) == 0:

            return self._fail(

                deduction=self.cfg.threshold("information", "entity_missing_deduction"),

                evidence={"text_count": 0},

                explanation="卡片中未检测到文本内容",

                suggestion="确保关键信息以文本形式呈现",

            )



        return self._pass({"text_count": len(ctx.text_elements)})
