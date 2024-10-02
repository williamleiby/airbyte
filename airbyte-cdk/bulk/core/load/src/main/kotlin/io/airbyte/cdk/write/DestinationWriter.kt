/*
 * Copyright (c) 2024 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.cdk.write

import io.airbyte.cdk.command.DestinationStream
import io.micronaut.context.annotation.Secondary
import jakarta.inject.Singleton

/**
 * Implementor interface. Every Destination must extend this and at least provide an implementation
 * of [createStreamLoader].
 */
interface DestinationWriter {
    // Called once before anything else
    suspend fun setup() {}

    // Return a StreamLoader for the given stream
    fun createStreamLoader(stream: DestinationStream): StreamLoader

    // Called once at the end of the job, unconditionally.
    suspend fun teardown(succeeded: Boolean = true) {}
}

@Singleton
@Secondary
class DefaultDestinationWriter : DestinationWriter {
    init {
        throw NotImplementedError(
            "DestinationWrite not implemented. Please create a custom @Singleton implementation."
        )
    }

    override fun createStreamLoader(stream: DestinationStream): StreamLoader {
        throw NotImplementedError()
    }
}
