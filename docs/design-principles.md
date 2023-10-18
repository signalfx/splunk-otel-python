# Design Principles

## What are our end goals?

The splunk-otel-python repo should be small, easy to understand, and well
tested.

#### Small

As simple as possible but no simpler. The end goal may be for this repo to
become so small that it disappears altogether and is no longer needed.
Everything we might want to put into this repo could, over the long term, be
put into upstream.

#### Easy to understand

Both production code and tests should require minimal cognitive load when
reading, extending, or modifying the code. This applies to both developers and
end users. Often this means reducing the scope of modules, where a module can
be a file, class, or function.

#### Well tested

Test coverage should be close to 100%, not just in terms of lines of code but
modes of usage. This is so we can refactor and add capabilities with confidence.
Furthermore, unit tests should run instantly (full speed, no sleeps) and
integration tests (which can take a long time, sleep, spin up containers etc.)
should test performance and correctness while using services external to the
system under test.

## SOLID

SOLID is sometimes used to describe a set of design principles.

- Single Responsibility Principle (SRP)
- Open/Closed Principle (OCP)
- Liskov Substitution Principle
- Interface Segregation Principle
- Dependency Inversion Principle (DIP)

I think the salient ones are SRP, OCP, and DIP.

#### SRP

Classes and functions should Do One Thing, and do it Only. A natural result of
this is that classes and functions will be small.

#### OCP

A class should be open for extension but closed for modification. What does
this mean? It means that you should design your classes (although this
priniciple can apply to functions too!) so that you can pass in the behavior
you want at runtime. e.g. a constructor able to accept an GRPC client instance
or a JSON HTTP client instance, or later, some other instance whose protocol
hasn't even been invented yet.

#### DIP

High-level (where 'level' generally means closer to the hardware) modules
should not depend on low-level modules. Both should depend on abstractions.
Additionally, abstractions should not depend on details; details should depend
on abstractions. This principle aims to decouple software modules to make the
system easier to manage and scale.

### Discussion

##### Is SOLID something just for Java or C# programmers?

The SOLID principles, while often associated with statically-typed languages
like Java or C#, are about good software design. Although Python, being
dynamic, is more flexible than static languages, projects written in Python
benefit from the maintainability advantages of SOLID design principles, because
SOLID is not about the language, but the developer.

## Agile

What does Agile mean for a repo like splunk-otel-python?

It means taking on small, incremental changes over shorter time intervals.
Instead of working on a large change over a longer time, make smaller changes,
each of which is a valid and fully tested increment. That means that sometimes
a change has to be considered in the context that it may not reflect the
author's desired end-state of the system. This makes work easier to plan,
schedule, execute, review, and measure.
