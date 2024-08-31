#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

import logging
from abc import ABC
from typing import Any, Iterator, List, Mapping, MutableMapping, Optional, Union

from airbyte_cdk.models import AirbyteMessage, AirbyteStateMessage, ConfiguredAirbyteCatalog
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.concurrent_source.concurrent_source import ConcurrentSource
from airbyte_cdk.sources.connector_state_manager import ConnectorStateManager
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.concurrent.abstract_stream import AbstractStream
from airbyte_cdk.sources.streams.concurrent.abstract_stream_facade import AbstractStreamFacade
from airbyte_cdk.sources.streams.concurrent.adapters import StreamFacade
from airbyte_cdk.sources.streams.concurrent.cursor import ConcurrentCursor, Cursor, FinalStateCursor


class ConcurrentSourceAdapter(AbstractSource, ABC):
    def __init__(self, concurrent_source: ConcurrentSource, **kwargs: Any) -> None:
        """
        ConcurrentSourceAdapter is a Source that wraps a concurrent source and exposes it as a regular source.

        The source's streams are still defined through the streams() method.
        Streams wrapped in a StreamFacade will be processed concurrently.
        Other streams will be processed sequentially as a later step.
        """
        self._concurrent_source = concurrent_source
        super().__init__(**kwargs)

    def read(
        self,
        logger: logging.Logger,
        config: Mapping[str, Any],
        catalog: ConfiguredAirbyteCatalog,
        state: Optional[Union[List[AirbyteStateMessage], MutableMapping[str, Any]]] = None,
    ) -> Iterator[AirbyteMessage]:
        abstract_streams = self._select_abstract_streams(config, catalog)
        concurrent_stream_names = {stream.name for stream in abstract_streams}
        configured_catalog_for_regular_streams = ConfiguredAirbyteCatalog(
            streams=[stream for stream in catalog.streams if stream.stream.name not in concurrent_stream_names]
        )
        if abstract_streams:
            yield from self._concurrent_source.read(abstract_streams)
        if configured_catalog_for_regular_streams.streams:
            yield from super().read(logger, config, configured_catalog_for_regular_streams, state)  # type: ignore[arg-type]

    def _select_abstract_streams(self, config: Mapping[str, Any], configured_catalog: ConfiguredAirbyteCatalog) -> List[AbstractStream]:
        """
        Selects streams that can be processed concurrently and returns their abstract representations.
        """
        all_streams = self.streams(config)
        stream_name_to_instance: Mapping[str, Stream] = {s.name: s for s in all_streams}
        abstract_streams: List[AbstractStream] = []
        for configured_stream in configured_catalog.streams:
            stream_instance = stream_name_to_instance.get(configured_stream.stream.name)
            if not stream_instance:
                continue

            if isinstance(stream_instance, AbstractStreamFacade):
                abstract_streams.append(stream_instance.get_underlying_stream())
        return abstract_streams

    def _convert_to_concurrent_stream(
        self, config: Mapping[str, Any], stream: Stream, state_manager: ConnectorStateManager, cursor: Optional[Cursor] = None
    ) -> Stream:
        """
        Prepares a stream for concurrent processing by initializing or assigning a cursor,
        managing the stream's state, and returning an updated Stream instance.

        :param config: Configuration parameters necessary for setting up the stream for concurrent processing.
        :type config: Mapping[str, Any]

        :param stream: The stream object that needs to be prepared for concurrent processing.
        :type stream: Stream

        :param state_manager: Responsible for managing the storage and retrieval of the stream's state.
        :type state_manager: ConnectorStateManager

        :param cursor: An optional cursor to manage stream state and processing boundaries.
        :type cursor: Optional[ConcurrentCursor]

        :return: A Stream instance configured for concurrent processing.
        :rtype: Stream
        """
        logger = logging.getLogger("airbyte")

        if cursor:
            state = cursor.state

            if hasattr(stream, "set_cursor") and stream.cursor_field:
                stream.set_cursor(cursor)

            if cursor and hasattr(stream, "parent") and hasattr(stream.parent, "set_cursor"):
                stream.parent.set_cursor(cursor)
        else:
            state = {}
            cursor = FinalStateCursor(
                stream_name=stream.name,
                stream_namespace=stream.namespace,
                message_repository=self.message_repository,  # type: ignore[arg-type]  # _default_message_repository will be returned in the worst case
            )

        return StreamFacade.create_from_stream(stream, self, logger, state, cursor)
