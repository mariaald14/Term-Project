from werkzeug.security import check_password_hash
# Chain of Responsibility Pattern
# This pattern is used when a user forgets their password
# The user must answer the three security questions from registration
# Each handler is responsible for checking one answer
# If the answer is correct the request moves to the next handler
# If an answer is wrong the checking stops
# The password can only be changed after all three answers are correct

# The base handler saves the next question and gives
# each question the same check method
class SecurityQuestionHandler:
    def __init__(self):
        self.next_handler = None

    def set_next(self, next_handler):
        # Save which question handler should run after
        # this one
        self.next_handler = next_handler

    def check_next(self, user, answers):
        # If there is another question, send the answers to
        # it, otherwise the chain is done
        if self.next_handler is not None:
            return self.next_handler.check(user, answers)
        return True

    def check(self, user, answers):
        raise NotImplementedError


class FirstQuestionHandler(SecurityQuestionHandler):
    def check(self, user, answers):
        # Check answer one and only move to the second handler if it is correct
        answer = answers[0].strip().lower()
        if not check_password_hash(user['answer1'], answer):
            return False
        return self.check_next(user, answers)


class SecondQuestionHandler(SecurityQuestionHandler):
    def check(self, user, answers):
        # Check answer two and only move to the third handler if it is correct
        answer = answers[1].strip().lower()
        if not check_password_hash(user['answer2'], answer):
            return False
        return self.check_next(user, answers)


class ThirdQuestionHandler(SecurityQuestionHandler):
    def check(self, user, answers):
        # Check the third answer because all three must be right to reset a password
        answer = answers[2].strip().lower()
        if not check_password_hash(user['answer3'], answer):
            return False
        return self.check_next(user, answers)


def check_recovery_answers(user, answers):
    # Link the first, second, and third handlers in order before checking the answers
    first = FirstQuestionHandler()
    second = SecondQuestionHandler()
    third = ThirdQuestionHandler()

    first.set_next(second)
    second.set_next(third)

    return first.check(user, answers)
