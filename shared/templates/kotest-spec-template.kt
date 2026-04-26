// Template: KoTest BehaviorSpec
// Source: https://kotest.io/docs/framework/testing-styles.html#behavior-spec
//
// Replace <Aggregate>, <Behavior>, <invariant> with concrete names.
// One file per aggregate or use case under test.
// Convention in webstack: place under `src/test/kotlin/<package>/<aggregate>/<Aggregate>Spec.kt`.

package com.example.<project>.domain.<aggregate>

import io.kotest.core.spec.style.BehaviorSpec
import io.kotest.matchers.shouldBe
import io.kotest.matchers.should
import io.kotest.matchers.types.shouldBeInstanceOf
import io.kotest.assertions.throwables.shouldThrow

class <Aggregate>Spec : BehaviorSpec({

    given("a fresh <Aggregate>") {
        val subject = <Aggregate>(/* defaults */)

        `when`("<action that triggers behavior>") {
            // act
            val result = subject.<action>(/* args */)

            then("<observable outcome>") {
                result shouldBe /* expected */
            }

            and("<additional invariant holds>") {
                subject.<state>.shouldBeInstanceOf</* expected type */>()
            }
        }

        `when`("<action that should fail>") {
            then("throws <ExpectedException> with helpful message") {
                shouldThrow<IllegalArgumentException> {
                    subject.<action>(/* invalid args */)
                }.message shouldBe "<expected message>"
            }
        }
    }

    given("an <Aggregate> in <specific state>") {
        val subject = <Aggregate>(/* configured to state */)

        `when`("<state-specific action>") {
            then("<state-specific outcome>") {
                // ...
            }
        }
    }
})
