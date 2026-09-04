import type { Meta } from "../types";

/** As limitações do modelo ficam dentro do produto, por escrito. */
export function HowToRead({ meta }: { meta: Meta }) {
  const m = meta.model_metrics;
  const fmt = (v: number | undefined) =>
    v === undefined ? "—" : v.toFixed(2).replace(".", ",");

  return (
    <div className="reader">
      <h3>O que o score é</h3>
      <p>
        O score é a probabilidade, segundo o modelo, de um artista atender ao critério de
        relevância da praça: ter aparecido no chart nos últimos 90 dias <b>e</b> estar entre os 10%
        de maior volume de streams naquele país. É uma leitura de relevância no streaming.
      </p>
      <h3>O que o score não é</h3>
      <p>
        Não é previsão de bilheteria, de público pagante nem de cachê. Streaming e venda de
        ingresso são coisas diferentes, e nada na base mede a segunda. Use o score para ordenar
        candidatos e descartar quem não tem lastro — não para decidir sozinho quem sobe no palco.
      </p>

      <h3>Por que faixas em vez de número</h3>
      <p>
        No conjunto de teste, quando o modelo aponta um artista como “forte”, ele acerta em cerca
        de metade das vezes. Mostrar “94,77” sugeriria uma precisão que o modelo não tem. As
        faixas comunicam a mesma ordenação sem prometer exatidão; o número exato aparece na ficha,
        arredondado.
      </p>

      <h3>Desempenho medido</h3>
      <table>
        <tbody>
          <tr>
            <td>F1 macro no teste (Random Forest)</td>
            <td className="mono">{fmt(m.rf_f1_macro_test)}</td>
          </tr>
          <tr>
            <td>F1 macro em validação cruzada</td>
            <td className="mono">{fmt(m.rf_cv_f1_macro)}</td>
          </tr>
          <tr>
            <td>F1 macro no teste (XGBoost)</td>
            <td className="mono">{fmt(m.xgb_f1_macro_test)}</td>
          </tr>
          <tr>
            <td>Precisão na classe “forte”</td>
            <td className="mono">{fmt(m.high_precision_test)}</td>
          </tr>
          <tr>
            <td>F1 na classe intermediária</td>
            <td className="mono">{fmt(m.medium_f1_test)}</td>
          </tr>
        </tbody>
      </table>
      <p className="note">
        Score gerado por {meta.model_used_for_score ?? "Random Forest"}. A classe prevista pelo
        modelo não aparece em lugar nenhum do produto: com F1 de {fmt(m.medium_f1_test)} na faixa
        intermediária, ela não tem qualidade para orientar decisão.
      </p>

      <h3>Limites dos dados</h3>
      <ul>
        <li>
          A base vai de {meta.window_start} a {meta.window_end}. “Ativo” significa ativo em
          relação a essa data de corte, não a hoje.
        </li>
        <li>
          Ouvintes mensais vêm do perfil global do Spotify: o mesmo número aparece nas cinco
          praças, mesmo quando a relevância local é bem diferente. Para força local, olhe streams
          na janela e a barra de força por praça.
        </li>
        <li>
          Só cinco praças foram processadas: Brasil, Estados Unidos, Reino Unido, México e
          Argentina.
        </li>
        <li>
          Um mesmo artista pode ter mais de um perfil no Spotify. Esses perfis foram consolidados
          por nome dentro de cada praça; a ficha avisa quando houve consolidação.
        </li>
      </ul>

      {meta.is_fixture && (
        <>
          <h3>Estes dados são de demonstração</h3>
          <p>{meta.fixture_notice}</p>
        </>
      )}
    </div>
  );
}
