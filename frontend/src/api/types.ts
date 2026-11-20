import type { components } from './schema';

type Schemas = components['schemas'];

export type Bank = Schemas['BankDTO'];
export type ClientCard = Schemas['ClientCardDTO'];
export type LocalizedText = Schemas['LocalizedTextDTO'];
export type Product = Schemas['ProductDTO'];
export type SessionCreated = Schemas['SessionCreatedDTO'];
export type SessionPublic = Schemas['SessionPublicDTO'];
export type SessionModels = Schemas['SessionModelsDTO'];
export type SessionStatus = Schemas['SessionStatus'];
export type Turn = Schemas['TurnDTO'];
export type MessageResult = Schemas['MessageResultDTO'];
export type WrapUpRequest = Schemas['WrapUpDTO'];
export type Language = Schemas['CreateSessionDTO']['language'];
