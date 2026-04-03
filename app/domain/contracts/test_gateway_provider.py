"""
TDD Red-фаза: тесты для абстрактного контракта GatewayProvider.

Тестируемый модуль (из gateway_provider.py):
  - GatewayProvider — абстрактный базовый класс (ABC), определяющий
    интерфейс для адаптеров внешних LLM-провайдеров.

Спецификация: contracts_spec.md

Проверяемые инварианты:
  1. GatewayProvider наследует abc.ABC.
  2. Нельзя создать экземпляр GatewayProvider напрямую (TypeError).
  3. Абстрактное свойство provider_name (str).
  4. Абстрактные async-методы: send_prompt, create_guardrail,
     update_guardrail, delete_guardrail, list_guardrails.
  5. Конкретная реализация, покрывающая все абстрактные методы,
     успешно инстанцируется и вызывается.
"""

from __future__ import annotations

import abc
import inspect
import uuid
from typing import Union

import pytest

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import MessageItem, UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse


# ==========================================================================
# Фикстуры
# ==========================================================================


@pytest.fixture()
def valid_trace_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def sample_prompt(valid_trace_id: str) -> UnifiedPrompt:
    return UnifiedPrompt(
        trace_id=valid_trace_id,
        model="gpt-4o",
        messages=[MessageItem(role="user", content="Привет!")],
    )


@pytest.fixture()
def sample_response(valid_trace_id: str) -> UnifiedResponse:
    return UnifiedResponse(
        trace_id=valid_trace_id,
        content="Ответ от модели",
        model="gpt-4o",
    )


@pytest.fixture()
def sample_error(valid_trace_id: str) -> GatewayError:
    return GatewayError(
        trace_id=valid_trace_id,
        error_code=GatewayError.PROVIDER_ERROR,
        message="Что-то пошло не так",
        status_code=500,
    )


class _ConcreteProvider(GatewayProvider):
    """Минимальная конкретная реализация для тестирования контракта."""

    @property
    def provider_name(self) -> str:
        return "test-provider"

    async def send_prompt(
        self, prompt: UnifiedPrompt, api_key: str, base_url: str
    ) -> Union[UnifiedResponse, GatewayError]:
        return UnifiedResponse(
            trace_id=prompt.trace_id,
            content="test response",
            model=prompt.model,
        )

    async def create_guardrail(
        self, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        return {"remote_id": "gr-001"}

    async def update_guardrail(
        self, remote_id: str, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        return {"remote_id": remote_id, "updated": True}

    async def delete_guardrail(
        self, remote_id: str, api_key: str, base_url: str
    ) -> Union[bool, GatewayError]:
        return True

    async def list_guardrails(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        return []


@pytest.fixture()
def concrete_provider() -> _ConcreteProvider:
    return _ConcreteProvider()


# ==========================================================================
# GatewayProvider — является ABC
# ==========================================================================


class TestGatewayProviderIsABC:
    """GatewayProvider ДОЛЖЕН наследовать abc.ABC."""

    def test_inherits_abc(self) -> None:
        assert issubclass(GatewayProvider, abc.ABC)

    def test_abc_in_mro(self) -> None:
        assert abc.ABC in GatewayProvider.__mro__

    def test_has_abstract_methods(self) -> None:
        """У GatewayProvider должны быть зарегистрированные абстрактные методы."""
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert len(abstracts) > 0, "GatewayProvider не содержит абстрактных методов"


# ==========================================================================
# GatewayProvider — нельзя инстанцировать напрямую
# ==========================================================================


class TestGatewayProviderCannotInstantiate:
    """[SRE_MARKER] — прямое создание GatewayProvider обходит контракт."""

    def test_direct_instantiation_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            GatewayProvider()

    def test_partial_implementation_raises_type_error(self) -> None:
        """Неполная реализация тоже не должна инстанцироваться."""

        class _Incomplete(GatewayProvider):
            @property
            def provider_name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError):
            _Incomplete()

    def test_missing_single_method_raises_type_error(self) -> None:
        """Пропуск хотя бы одного абстрактного метода — TypeError."""

        class _MissingSendPrompt(GatewayProvider):
            @property
            def provider_name(self) -> str:
                return "missing-send"

            async def create_guardrail(self, config, api_key, base_url):
                pass

            async def update_guardrail(self, remote_id, config, api_key, base_url):
                pass

            async def delete_guardrail(self, remote_id, api_key, base_url):
                pass

            async def list_guardrails(self, api_key, base_url):
                pass

        with pytest.raises(TypeError):
            _MissingSendPrompt()


# ==========================================================================
# GatewayProvider — свойство provider_name
# ==========================================================================


class TestGatewayProviderName:
    """Свойство provider_name должно быть абстрактным и возвращать str."""

    def test_provider_name_is_abstract(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert "provider_name" in abstracts

    def test_provider_name_is_property(self) -> None:
        """provider_name должен быть определён как property (дескриптор)."""
        attr = inspect.getattr_static(GatewayProvider, "provider_name")
        assert isinstance(attr, property), (
            f"provider_name должен быть property, а не {type(attr).__name__}"
        )

    def test_concrete_provider_name_returns_str(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        name = concrete_provider.provider_name
        assert isinstance(name, str)
        assert name == "test-provider"


# ==========================================================================
# GatewayProvider — метод send_prompt
# ==========================================================================


class TestSendPromptContract:
    """Абстрактный async-метод send_prompt(prompt, api_key, base_url)."""

    def test_send_prompt_is_abstract(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert "send_prompt" in abstracts

    def test_send_prompt_is_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(getattr(GatewayProvider, "send_prompt")), (
            "send_prompt должен быть async def"
        )

    def test_send_prompt_signature(self) -> None:
        """Сигнатура: (self, prompt: UnifiedPrompt, api_key: str, base_url: str)."""
        sig = inspect.signature(GatewayProvider.send_prompt)
        params = list(sig.parameters.keys())
        assert params == ["self", "prompt", "api_key", "base_url"], (
            f"Ожидаемые параметры: ['self', 'prompt', 'api_key', 'base_url'], "
            f"получены: {params}"
        )

    @pytest.mark.asyncio
    async def test_concrete_send_prompt_returns_unified_response(
        self, concrete_provider: _ConcreteProvider, sample_prompt: UnifiedPrompt
    ) -> None:
        result = await concrete_provider.send_prompt(
            prompt=sample_prompt, api_key="sk-test", base_url="https://api.test.com"
        )
        assert isinstance(result, (UnifiedResponse, GatewayError))
        assert isinstance(result, UnifiedResponse)
        assert result.trace_id == sample_prompt.trace_id


# ==========================================================================
# GatewayProvider — метод create_guardrail
# ==========================================================================


class TestCreateGuardrailContract:
    """Абстрактный async-метод create_guardrail(config, api_key, base_url)."""

    def test_create_guardrail_is_abstract(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert "create_guardrail" in abstracts

    def test_create_guardrail_is_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(
            getattr(GatewayProvider, "create_guardrail")
        ), "create_guardrail должен быть async def"

    def test_create_guardrail_signature(self) -> None:
        """Сигнатура: (self, config: dict, api_key: str, base_url: str)."""
        sig = inspect.signature(GatewayProvider.create_guardrail)
        params = list(sig.parameters.keys())
        assert params == ["self", "config", "api_key", "base_url"]

    @pytest.mark.asyncio
    async def test_concrete_create_guardrail_returns_dict(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        result = await concrete_provider.create_guardrail(
            config={"name": "test-policy"},
            api_key="sk-test",
            base_url="https://api.test.com",
        )
        assert isinstance(result, (dict, GatewayError))
        assert isinstance(result, dict)
        assert "remote_id" in result


# ==========================================================================
# GatewayProvider — метод update_guardrail
# ==========================================================================


class TestUpdateGuardrailContract:
    """Абстрактный async-метод update_guardrail(remote_id, config, api_key, base_url)."""

    def test_update_guardrail_is_abstract(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert "update_guardrail" in abstracts

    def test_update_guardrail_is_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(
            getattr(GatewayProvider, "update_guardrail")
        ), "update_guardrail должен быть async def"

    def test_update_guardrail_signature(self) -> None:
        """Сигнатура: (self, remote_id: str, config: dict, api_key: str, base_url: str)."""
        sig = inspect.signature(GatewayProvider.update_guardrail)
        params = list(sig.parameters.keys())
        assert params == ["self", "remote_id", "config", "api_key", "base_url"]

    @pytest.mark.asyncio
    async def test_concrete_update_guardrail_returns_dict(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        result = await concrete_provider.update_guardrail(
            remote_id="gr-001",
            config={"name": "updated-policy"},
            api_key="sk-test",
            base_url="https://api.test.com",
        )
        assert isinstance(result, (dict, GatewayError))
        assert isinstance(result, dict)


# ==========================================================================
# GatewayProvider — метод delete_guardrail
# ==========================================================================


class TestDeleteGuardrailContract:
    """Абстрактный async-метод delete_guardrail(remote_id, api_key, base_url)."""

    def test_delete_guardrail_is_abstract(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert "delete_guardrail" in abstracts

    def test_delete_guardrail_is_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(
            getattr(GatewayProvider, "delete_guardrail")
        ), "delete_guardrail должен быть async def"

    def test_delete_guardrail_signature(self) -> None:
        """Сигнатура: (self, remote_id: str, api_key: str, base_url: str)."""
        sig = inspect.signature(GatewayProvider.delete_guardrail)
        params = list(sig.parameters.keys())
        assert params == ["self", "remote_id", "api_key", "base_url"]

    @pytest.mark.asyncio
    async def test_concrete_delete_guardrail_returns_bool(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        result = await concrete_provider.delete_guardrail(
            remote_id="gr-001",
            api_key="sk-test",
            base_url="https://api.test.com",
        )
        assert isinstance(result, (bool, GatewayError))
        assert result is True


# ==========================================================================
# GatewayProvider — метод list_guardrails
# ==========================================================================


class TestListGuardrailsContract:
    """Абстрактный async-метод list_guardrails(api_key, base_url)."""

    def test_list_guardrails_is_abstract(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        assert "list_guardrails" in abstracts

    def test_list_guardrails_is_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(
            getattr(GatewayProvider, "list_guardrails")
        ), "list_guardrails должен быть async def"

    def test_list_guardrails_signature(self) -> None:
        """Сигнатура: (self, api_key: str, base_url: str)."""
        sig = inspect.signature(GatewayProvider.list_guardrails)
        params = list(sig.parameters.keys())
        assert params == ["self", "api_key", "base_url"]

    @pytest.mark.asyncio
    async def test_concrete_list_guardrails_returns_list(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        result = await concrete_provider.list_guardrails(
            api_key="sk-test",
            base_url="https://api.test.com",
        )
        assert isinstance(result, (list, GatewayError))
        assert isinstance(result, list)


# ==========================================================================
# GatewayProvider — полнота абстрактных методов
# ==========================================================================


class TestGatewayProviderAbstractCompleteness:
    """Все ожидаемые абстрактные члены должны быть зарегистрированы."""

    EXPECTED_ABSTRACT_MEMBERS = frozenset(
        {
            "provider_name",
            "send_prompt",
            "create_guardrail",
            "update_guardrail",
            "delete_guardrail",
            "list_guardrails",
        }
    )

    def test_all_expected_abstracts_present(self) -> None:
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        missing = self.EXPECTED_ABSTRACT_MEMBERS - abstracts
        assert not missing, f"Отсутствуют абстрактные члены: {missing}"

    def test_no_unexpected_abstracts(self) -> None:
        """[SRE_MARKER] — неожиданные абстрактные методы нарушают контракт адаптеров."""
        abstracts = getattr(GatewayProvider, "__abstractmethods__", set())
        extra = abstracts - self.EXPECTED_ABSTRACT_MEMBERS
        assert not extra, f"Обнаружены лишние абстрактные члены: {extra}"


# ==========================================================================
# GatewayProvider — конкретная реализация работает
# ==========================================================================


class TestConcreteProviderInstantiation:
    """Полная конкретная реализация должна успешно инстанцироваться."""

    def test_concrete_provider_instantiates(self) -> None:
        provider = _ConcreteProvider()
        assert provider is not None

    def test_concrete_provider_is_instance_of_gateway_provider(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        assert isinstance(concrete_provider, GatewayProvider)

    def test_concrete_provider_is_instance_of_abc(
        self, concrete_provider: _ConcreteProvider
    ) -> None:
        assert isinstance(concrete_provider, abc.ABC)


# ==========================================================================
# GatewayProvider — изоляция от инфраструктурных слоёв
# ==========================================================================


class TestGatewayProviderDomainIsolation:
    """[SRE_MARKER] — контракт НЕ должен импортировать infrastructure/services/api."""

    def test_module_does_not_import_infrastructure(self) -> None:
        import app.domain.contracts.gateway_provider as mod

        source = inspect.getsource(mod)
        assert "infrastructure" not in source, (
            "gateway_provider.py не должен импортировать из infrastructure"
        )

    def test_module_does_not_import_services(self) -> None:
        import app.domain.contracts.gateway_provider as mod

        source = inspect.getsource(mod)
        assert "services" not in source, (
            "gateway_provider.py не должен импортировать из services"
        )

    def test_module_does_not_import_api(self) -> None:
        import app.domain.contracts.gateway_provider as mod

        source = inspect.getsource(mod)
        # Проверяем именно "from app.api" или "import app.api", а не просто "api"
        # т.к. "api_key" — допустимый параметр
        assert "from app.api" not in source, (
            "gateway_provider.py не должен импортировать из app.api"
        )
        assert "import app.api" not in source, (
            "gateway_provider.py не должен импортировать app.api"
        )
