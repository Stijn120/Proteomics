import streamlit as st
import pandas as pd
from typing import Tuple
from pathlib import Path

from sklearn.preprocessing import MultiLabelBinarizer

from analysis import filter_on_peptide_count, \
    get_protein_frequency, \
    add_gini_impurity, \
    get_identifying_proteins, \
    pure_mixture_diff, \
    get_protein_intensity, \
    add_mean_protein_intensity, \
    general_statistics
from constants import BODY_FLUIDS
from visualize import protein_counts_per_fluid_dist
from utils import (preprocess_df, exclude_samples, get_sample_columns,
                   style_df)
from model import run_tsne
from model import RelativeProteinFrequencyModel, prepare_data, \
    classification_report, visualize_metrics


@st.cache_data
def load_data(pure_file_path: Path,
              combi_file_path: Path) -> Tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pure_peptide_df = pd.read_excel(pure_file_path,
                                    sheet_name='2581_PureOnly_Peptide')
    pure_protein_df = pd.read_excel(pure_file_path,
                                    sheet_name='2581_PureOnly_Protein')
    mixture_peptide_df = pd.read_excel(combi_file_path,
                                       sheet_name='2581_CombiOnly_Peptide')

    return pure_peptide_df, pure_protein_df, mixture_peptide_df


if __name__ == '__main__':
    # Set wide page layout
    st.set_page_config(layout="wide")

    # Set samples to exclude
    st.session_state['samples_to_exclude'] = None

    # Upload file
    st.header("Upload files")
    pure_file = st.file_uploader(label="PureOnly file",
                                 type='.xlsx')
    combi_file = st.file_uploader(label="CombiOnly file",
                                  type='.xlsx')

    # Peptide threshold
    peptide_threshold = st.number_input("Peptide threshold "
                                        "(nr of peptides >= "
                                        "peptide threshold)",
                                        value=3,
                                        key='peptide_threshold')

    # When file uploaded
    if pure_file is not None and combi_file is not None:

        # Read data into dataframes
        (pure_pep_df_o,
         pure_prot_df_o,
         mix_pep_df_o) = load_data(pure_file, combi_file)

        # Simplify sample column names
        pure_pept_df = preprocess_df(pure_pep_df_o)
        mix_pep_df = preprocess_df(mix_pep_df_o)
        pure_prot_df = preprocess_df(pure_prot_df_o)

        st.divider()

        # Create column layout for basic info
        gen_info_column, exclude_sample_column = st.columns(2)

        st.divider()

        # Provide option to select samples to exclude
        with exclude_sample_column:
            st.subheader("Select samples to exclude:")
            st.multiselect('Pure samples to exclude',
                           get_sample_columns(pure_pept_df),
                           key='pure_samples_to_exclude'
                           )
            st.multiselect('Mixed samples to exclude',
                           get_sample_columns(mix_pep_df),
                           key='mixed_samples_to_exclude'
                           )

        # Filter on samples to exclude
        if st.session_state["pure_samples_to_exclude"] is not None:
            pure_pept_df = exclude_samples(
                pure_pept_df,
                st.session_state["pure_samples_to_exclude"]
            )
            pure_prot_df = exclude_samples(
                pure_prot_df,
                st.session_state["pure_samples_to_exclude"]
            )
        if st.session_state["mixed_samples_to_exclude"] is not None:
            mix_pep_df = exclude_samples(
                mix_pep_df,
                st.session_state["mixed_samples_to_exclude"]
            )

        # Filter on proteins that have at least n detected peptides per sample
        pure_protein_df = filter_on_peptide_count(
            pure_pept_df,
            st.session_state["peptide_threshold"]
        )
        mix_protein_df = filter_on_peptide_count(
            mix_pep_df,
            st.session_state["peptide_threshold"]
        )

        # Get protein intensities
        protein_intensities = get_protein_intensity(
            pure_prot_df,
            pure_protein_df
        )

        # Add relative nr of times each protein occurs in a body fluid
        protein_frequency = get_protein_frequency(pure_protein_df)

        # Calculate information gain per protein
        (protein_frequency, proteins_in_no_samples_per_body_fluid) = (
            add_gini_impurity(protein_frequency)
        )

        # Add protein intensities
        protein_frequency = (
            add_mean_protein_intensity(protein_frequency,
                                       protein_intensities)
        )

        # Show general statistics
        with gen_info_column:
            st.subheader("General info")
            st.dataframe(general_statistics(pure_protein_df))

        # Show protein frequency
        st.subheader("Protein frequency per body fluid")
        st.write(style_df(protein_frequency))

        # Get identifying proteins per body fluid
        identifying_proteins = get_identifying_proteins(
            protein_frequency
        )

        # Get differences in proteins between pure fluids and mixture samples
        pure_mix_differences = pure_mixture_diff(pure_protein_df,
                                                 mix_protein_df)

        # Show specific results per fluid
        st.divider()
        st.header("Analysis per body fluid")

        # Fluid selection
        selected_fluid = st.radio("Body fluid selection",
                                  BODY_FLUIDS,
                                  horizontal=True)
        if selected_fluid is not None:
            # Make separate df for this fluid
            identifying_proteins_fluid = identifying_proteins.loc[
                identifying_proteins['body fluid'] == selected_fluid]

            # Give nr of identifying proteins
            st.write(f"Found {len(identifying_proteins_fluid)} "
                     f"identifying proteins for {selected_fluid}:")

            # Show proteins specific for certain body fluids
            with st.expander("Identifying proteins", expanded=True):
                st.write(style_df(identifying_proteins
                                  [identifying_proteins
                                   ['body fluid'] == selected_fluid]
                                  .drop('body fluid', axis=1)
                                  )
                         )

            # Get mix differences specific for fluid
            fluid_pure_mix_differences = (
                pure_mix_differences).loc[
                pure_mix_differences['body fluid']
                == selected_fluid]

            # Filter out samples and get unique proteins
            fluid_pure_mix_differences = (
                fluid_pure_mix_differences
                .drop('mix sample', axis=1)
                .drop_duplicates()
            )

            # Show proteins that are present in mixture sample,
            # but not in pure sample
            with st.expander(
                    f"Proteins in mixture not in "
                    f"fluid for {selected_fluid}",
                    expanded=True):
                st.dataframe(
                    fluid_pure_mix_differences.loc[
                        ~fluid_pure_mix_differences['present in fluid'] &
                        fluid_pure_mix_differences['present in mixture']]
                )

            # Show proteins that are present in pure sample,
            # but not in mixture sample
            with st.expander(
                    f"Proteins in fluid not in "
                    f"mixture for {selected_fluid}",
                    expanded=True):
                st.dataframe(
                    fluid_pure_mix_differences.loc[
                        fluid_pure_mix_differences['present in fluid'] &
                        ~fluid_pure_mix_differences['present in mixture']]
                )

        # Visualizations
        st.divider()
        st.header("Visualizations")

        # Specify columns
        vis1, vis2 = st.columns(2)

        # Show T-SNE plot of pure samples
        with vis1:
            run_tsne(pure_protein_df, mix_protein_df)

        # Show protein counts per fluid distribution
        with vis2:
            protein_counts_per_fluid_dist(pure_protein_df)

        # Section for showing model results
        st.header("Modelling")

        # Perform predictions
        m = RelativeProteinFrequencyModel()
        m.fit(identifying_proteins)
        preds, scores = m.predict(mix_protein_df)
        mlb = MultiLabelBinarizer()
        preds_transformed = mlb.fit_transform(preds)

        x_test, y_test = prepare_data(mix_protein_df, multilabel=True)
        y_test_transformed = mlb.transform(y_test)

        metrics = classification_report(y_test_transformed,
                                        preds_transformed,
                                        output_dict=True,
                                        target_names=mlb.classes_)

        # Visualize metrics
        visualize_metrics(metrics)

        # Calculate and show false positives and negatives
        st.subheader("False Positives and False Negatives")
        sample_names = get_sample_columns(mix_protein_df)
        for i, (pred, y_test, score) in enumerate(zip(preds, y_test, scores)):
            if len(set(pred).difference(set(y_test))) > 0:
                st.write(sample_names[i])
                col1, col2 = st.columns(2)
                with col1:
                    st.write("Predicted")
                    st.write(pred)
                    st.write(score)
                with col2:
                    st.write("True")
                    st.write(y_test)
                    st.write(score)